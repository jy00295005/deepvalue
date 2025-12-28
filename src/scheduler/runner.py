import sys
import uuid
import json
from datetime import datetime
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert

from src.config.settings import UNIVERSE, MAG7_SYMBOLS
from src.data.store import DataStore, Run, PriceDaily
from src.data.ingestion import DataIngestion
from src.compute.features import FeatureEngine
from src.compute.levels import LevelsEngine
from src.compute.market_state import MarketStateEngine
from src.compute.policy import PolicyEngine
from src.llm.service import LLMService
from src.reporting.daily_report import DailyReportGenerator
from src.config.settings import ACCUMULATE_SCORE_MIN

class EODRunner:
    def __init__(self):
        self.store = DataStore()
        # Initialize DB if needed (idempotent)
        self.store.init_db()
        self.db = self.store.get_session()
        
        # Components
        self.ingestion = DataIngestion(self.store)
        self.features = FeatureEngine(self.store)
        self.levels = LevelsEngine(self.store)
        self.market_state = MarketStateEngine(self.store)
        self.policy = PolicyEngine(self.store)
        self.llm_service = LLMService(self.store)
        self.reporter = DailyReportGenerator(self.store, self.llm_service)

    def _start_run(self, mode: str = "daily_eod") -> str:
        run_id = str(uuid.uuid4())
        asof_date = datetime.utcnow().strftime('%Y-%m-%d')
        
        record = {
            'run_id': run_id,
            'asof_date': asof_date,
            'mode': mode,
            'status': 'started',
            'started_at': datetime.utcnow().isoformat()
        }
        
        stmt = insert(Run).values(record)
        self.db.execute(stmt)
        self.db.commit()
        logger.info(f"Started Run {run_id} ({mode})")
        return run_id, asof_date

    def _update_run(self, run_id: str, status: str, error: str = None):
        stmt = update(Run).where(Run.run_id == run_id).values(
            status=status,
            error=error,
            ended_at=datetime.utcnow().isoformat()
        )
        self.db.execute(stmt)
        self.db.commit()
        if error:
            logger.error(f"Run {run_id} failed: {error}")
        else:
            logger.info(f"Run {run_id} completed: {status}")

    def run_pipeline(self, symbols: list[str] = UNIVERSE):
        run_id, asof_date_utc = self._start_run()
        
        try:
            # 1. Ingestion
            logger.info("=== Stage 1: Ingestion ===")
            # Note: ingestion typically looks at history up to "now".
            # For strict determinism, we might want to cap it? 
            # But 'ingestion.run_ingestion' fetches last N years.
            self.ingestion.run_ingestion(symbols)
            
            # Determine "Latest Business Day" from data to run computations for.
            # Usually we run for "Today" if market closed.
            # Let's find the max date in prices_daily for our universe.
            # (Assuming ingestion just updated it)
            latest_date_row = self.db.execute(
                select(PriceDaily.date).where(PriceDaily.symbol.in_(symbols)).order_by(PriceDaily.date.desc()).limit(1)
            ).scalar_one_or_none()
            
            if not latest_date_row:
                raise ValueError("No data found after ingestion.")
            
            target_date = latest_date_row
            logger.info(f"Targeting computations for date: {target_date}")
            
            # 2. Compute Features
            logger.info("=== Stage 2: Features ===")
            self.features.run(symbols)
            
            # 3. Compute Levels
            logger.info("=== Stage 3: Levels ===")
            self.levels.run(symbols)
            
            # 3.5 PP Fusion (external support levels)
            logger.info("=== Stage 3.5: PP Fusion ===")
            try:
                pp_fused = self.levels.run_with_pp_fusion(symbols, target_date)
                self._pp_fused_levels = pp_fused  # Store for later use in strategy
                logger.info(f"PP fusion completed for {len(pp_fused)} symbols")
            except Exception as e:
                logger.warning(f"PP fusion skipped: {e}")
                self._pp_fused_levels = {}
            
            # 4. Compute Market State
            logger.info("=== Stage 4: Market State ===")
            self.market_state.run()
            
            # 5. Baseline Policy
            logger.info("=== Stage 5: Baseline Policy ===")
            self.policy.run(symbols)
            
            # 6. LLM Enhancement (Strategy)
            # We iterate symbols and upgrade baseline to LLM strategy if possible
            logger.info("=== Stage 6: LLM Strategy Enhancement ===")
            # Note: Policy engine only saved baseline. 
            # We need to fetch it, call LLM, and update RecommendationDaily.
            # Or we can do it inside PolicyEngine? 
            # Design doc separated them: "3) LLM (Controlled): Strategy Narrator".
            # Let's do it here or via a dedicated method in Policy/LLM service.
            # Let's iterate and update.
            
            self._enhance_strategies(target_date, symbols)
            
            # 7. Reporting
            logger.info("=== Stage 7: Reporting ===")
            report_md = self.reporter.generate_report(target_date, symbols)
            
            logger.success(f"Report Generated for {target_date}")
            # print(report_md) # Optional: print to stdout
            
            self._update_run(run_id, "success")
            
        except Exception as e:
            logger.exception("Pipeline failed")
            self._update_run(run_id, "failed", str(e))
            sys.exit(1)

    def _enhance_strategies(self, date_str: str, symbols: list[str]):
        """
        Fetch baseline, call LLM, update recommendation.
        """
        # Load necessary data
        # We need: baseline recommendation, features, levels, market state
        
        # Optimization: Helper in PolicyEngine or just SQL here?
        # Let's use PolicyEngine's helpers if possible, or just query.
        
        market = self.policy.get_market_state(date_str)
        if not market:
            logger.warning("No market state for strategy enhancement")
            return

        from src.data.store import RecommendationDaily

        batch_items: list[dict] = []
        baseline_by_symbol: dict[str, dict] = {}
        reco_by_symbol: dict[str, RecommendationDaily] = {}
        deterministic_by_symbol: dict[str, dict] = {}

        for symbol in symbols:
            if symbol not in MAG7_SYMBOLS:
                continue

            reco = self.db.execute(
                select(RecommendationDaily).where(
                    RecommendationDaily.symbol == symbol,
                    RecommendationDaily.date == date_str
                )
            ).scalar_one_or_none()
            if not reco:
                continue

            price_row, feature_row, level_row = self.policy.get_latest_data(symbol)
            if not (price_row and feature_row and level_row):
                continue

            price_val = price_row.adj_close if price_row.adj_close else price_row.close

            baseline_plan = {
                'action': reco.action,
                'plan_json': json.loads(reco.plan_json),
                'explain_json': json.loads(reco.explain_json)
            }

            # Use PP-fused levels if available, otherwise internal
            pp_fused = getattr(self, '_pp_fused_levels', {}).get(symbol, {})
            s1_final = pp_fused.get('s1', level_row.s1) or level_row.s1
            s2_final = pp_fused.get('s2', level_row.s2) or level_row.s2
            s3_final = pp_fused.get('s3', level_row.s3) or level_row.s3
            fusion_meta = pp_fused.get('fusion_meta', {})
            
            # Recompute distances with fused levels
            class FusedLevels:
                def __init__(self, s1, s2, s3, r1, r2, r3):
                    self.s1, self.s2, self.s3 = s1, s2, s3
                    self.r1, self.r2, self.r3 = r1, r2, r3
            fused_level_obj = FusedLevels(s1_final, s2_final, s3_final, level_row.r1, level_row.r2, level_row.r3)
            dists = self.policy.compute_distances(price_val, fused_level_obj)
            
            deterministic_data = {
                'symbol': symbol,
                'price': price_val,
                'is_adjusted': bool(price_row.adj_close),
                'score': feature_row.deepvalue_score_smooth,
                'market_regime': market.regime,
                'market_multiplier': market.multiplier,
                'baseline_action': reco.action,
                's1': s1_final, 's1_dist_pct': dists.get('s1_pct'),
                's2': s2_final, 's2_dist_pct': dists.get('s2_pct'),
                's3': s3_final, 's3_dist_pct': dists.get('s3_pct'),
                'r1': level_row.r1, 'r1_dist_pct': dists.get('r1_pct'),
                'pp_fusion_meta': fusion_meta,  # Include fusion info for LLM context
            }

            batch_items.append(deterministic_data)
            baseline_by_symbol[symbol] = baseline_plan
            reco_by_symbol[symbol] = reco
            deterministic_by_symbol[symbol] = deterministic_data

        strategies_by_symbol = self.llm_service.generate_strategies_batch(batch_items, baseline_by_symbol)

        for symbol, new_strategy in strategies_by_symbol.items():
            reco = reco_by_symbol.get(symbol)
            deterministic_data = deterministic_by_symbol.get(symbol, {})
            if not reco:
                continue

            # Deterministic enforcement: accumulate gate
            score_val = deterministic_data.get('score')
            if new_strategy.get('action') == 'accumulate' and score_val is not None and float(score_val) < float(ACCUMULATE_SCORE_MIN):
                new_strategy['action'] = 'hold'
                src = new_strategy.get('strategy_source') or new_strategy.get('source') or 'llm'
                new_strategy['strategy_source'] = src
                new_strategy['source'] = src
                reasons = new_strategy.get('reasons')
                if not isinstance(reasons, list):
                    reasons = []
                reasons.append(f"Action forced to hold: score {float(score_val):.1f} < ACCUMULATE_SCORE_MIN {ACCUMULATE_SCORE_MIN}")
                new_strategy['reasons'] = reasons
            
            # Update DB
            # Update action, plan_json, explain_json, llm_used
            # StrategyOutput structure: 
            # action, ladder_weights_pct, reserve_pct, avoid_chasing, reasons, confidence, source
            
            # We need to reconstruct plan_json with new weights
            # Preserve budget_multiplier from baseline
            current_plan = json.loads(reco.plan_json)
            current_plan['ladder_weights_pct'] = new_strategy['ladder_weights_pct']
            current_plan['reserve_pct'] = new_strategy['reserve_pct']
            current_plan['strategy_source'] = new_strategy.get('strategy_source') or new_strategy.get('source', 'llm')
            
            # Reconstruct explain
            current_explain = json.loads(reco.explain_json)
            current_explain['reasons'] = new_strategy['reasons']
            current_explain['confidence'] = new_strategy['confidence']
            current_explain['strategy_source'] = new_strategy.get('strategy_source') or new_strategy.get('source', 'llm')
            current_explain['source'] = current_explain['strategy_source']
            
            stmt = update(RecommendationDaily).where(
                RecommendationDaily.symbol == symbol,
                RecommendationDaily.date == date_str
            ).values(
                action=new_strategy['action'],
                plan_json=json.dumps(current_plan),
                explain_json=json.dumps(current_explain),
                llm_used=1 if (new_strategy.get('strategy_source') or new_strategy.get('source')) == 'llm' else 0
            )
            self.db.execute(stmt)
            self.db.commit()
            logger.info(f"Enhanced strategy for {symbol}: {new_strategy['source']}")


if __name__ == "__main__":
    runner = EODRunner()
    runner.run_pipeline()
