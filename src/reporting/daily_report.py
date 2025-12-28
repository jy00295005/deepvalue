import json
import pandas as pd
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from typing import List, Dict

from src.data.store import DataStore, MarketStateDaily, RecommendationDaily, FeatureDaily, LevelDaily, PriceDaily, Report
from src.llm.service import LLMService
from src.config.settings import CHEAP_THRESHOLD

class DailyReportGenerator:
    def __init__(self, store: DataStore, llm_service: LLMService):
        self.store = store
        self.db = store.get_session()
        self.llm = llm_service

    def get_data_for_date(self, date_str: str):
        # 1. Market State
        market = self.db.execute(
            select(MarketStateDaily).where(MarketStateDaily.date == date_str)
        ).scalar_one_or_none()
        
        # 2. Recommendations (includes baseline or LLM-enhanced)
        recos = self.db.execute(
            select(RecommendationDaily).where(RecommendationDaily.date == date_str)
        ).scalars().all()
        
        # 3. Features
        feats = self.db.execute(
            select(FeatureDaily).where(FeatureDaily.date == date_str)
        ).scalars().all()
        
        # 4. Levels (optional, for details if needed, but reco has plans)
        # We might want Levels to show S1/S2/S3 explicitly in table if not in reco plan?
        # Reco plan has 'ladder_weights_pct' but maybe not prices if LLM didn't output them?
        # Wait, StrategyOutput in validator DOES NOT have prices, only weights.
        # We need Levels to show the prices.
        levels = self.db.execute(
            select(LevelDaily).where(LevelDaily.date == date_str)
        ).scalars().all()
        
        return market, recos, feats, levels

    def _format_table(self, combined_data: List[Dict]) -> str:
        # Columns: Symbol, Score, Action, S1, S1 Dist
        # Sort by Score desc
        sorted_data = sorted(combined_data, key=lambda x: x['score'], reverse=True)
        
        md_lines = []
        md_lines.append("| Symbol | Score | Rank(5y) | Action | Reserve | Strategy | PP | PP Band | S1 Src | S2 Src | S3 Src | S1 Dist |")
        md_lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        
        for item in sorted_data:
            symbol = item['symbol']
            score = f"{item['score']:.0f}" if item['score'] is not None else "N/A"
            rank = f"{item['rank']:.2f}" if item['rank'] is not None else "N/A"
            action = item.get('action', 'hold')
            reserve_pct = item.get('reserve_pct')
            reserve_str = f"{int(reserve_pct)}%" if reserve_pct is not None else "-"
            strategy_source = item.get('strategy_source', '-')

            pp_status = item.get('pp_status', '-')
            pp_band = item.get('pp_band', '-')
            
            s1_src = item.get('s1_source', '-')
            s2_src = item.get('s2_source', '-')
            s3_src = item.get('s3_source', '-')
            
            # Calculate dist
            # We assume price is available in item or we compute it? 
            # We don't have current price here easily unless we passed it.
            # Let's trust we can grab it from Feature or separate query?
            # Actually, `s1_dist` might be needed.
            # Let's assume we pass dist or compute it.
            # For table summary, just showing Price vs S1 is good.
            # Let's compute dist if we have price.
            
            price = item.get('price')
            s1 = item.get('s1')
            if price and s1:
                # Distance % = (Level / Price) - 1
                # If S1 < Price, result is negative (e.g. -10% means need to drop 10% to hit S1)
                dist_pct = (s1 / price) - 1
                dist_str = f"{dist_pct:.1%}"
            else:
                dist_str = "-"
                
            md_lines.append(f"| {symbol} | {score} | {rank} | {action} | {reserve_str} | {strategy_source} | {pp_status} | {pp_band} | {s1_src} | {s2_src} | {s3_src} | {dist_str} |")
            
        return "\n".join(md_lines)

    def _parse_pp_info(self, meta_json: str) -> tuple[str, str]:
        """Return (pp_status, pp_band_str) from levels.s_meta."""
        if not meta_json:
            return "-", "-"
        try:
            meta = json.loads(meta_json)
            if not isinstance(meta, dict):
                return "-", "-"
            pp = meta.get('pp_fusion') or {}
            if not isinstance(pp, dict):
                return "-", "-"

            used = bool(pp.get('pp_used'))
            conf = pp.get('pp_confidence')
            conf_str = f"{float(conf):.2f}" if isinstance(conf, (int, float)) else "-"
            if used:
                status = f"used({conf_str})"
            else:
                reason = pp.get('pp_reason') or 'ignored'
                status = f"{reason}({conf_str})" if conf_str != "-" else str(reason)

            band = pp.get('pp_band') or {}
            if isinstance(band, dict) and band.get('low') is not None and band.get('high') is not None:
                band_str = f"{float(band['low']):.2f}-{float(band['high']):.2f}"
            else:
                band_str = "-"

            return status, band_str
        except Exception:
            return "-", "-"

    def _maybe_override_source_with_pp(self, meta_json: str, level_name: str, level_price: float, current_src: str) -> str:
        """If the current level matches selected_fused and fusion says it was calibrated, mark as pp_fused."""
        if not meta_json or level_price is None:
            return current_src
        try:
            meta = json.loads(meta_json)
            if not isinstance(meta, dict):
                return current_src
            pp = meta.get('pp_fusion') or {}
            sel = meta.get('selected_fused') or {}
            if not isinstance(pp, dict) or not isinstance(sel, dict):
                return current_src

            if level_name == 's1' and pp.get('s1_fusion') in ('pp_calibrated', 'pp_confirms'):
                fused_val = sel.get('s1')
            elif level_name == 's2' and pp.get('s2_fusion') == 'pp_replaced_weak':
                fused_val = sel.get('s2')
            else:
                return current_src

            if fused_val is None:
                return current_src
            fused_val_f = float(fused_val)
            level_val_f = float(level_price)
            if fused_val_f <= 0:
                return current_src
            rel = abs(fused_val_f - level_val_f) / fused_val_f
            if rel <= 0.002:
                return 'pp_fused'
        except Exception:
            return current_src
        return current_src

    def _parse_level_source(self, meta_json: str, level_price: float) -> str:
        if not meta_json or level_price is None:
            return "-"
        try:
            meta = json.loads(meta_json)
            cands = meta.get('candidates', []) if isinstance(meta, dict) else []
            best = None
            for c in cands:
                try:
                    p = float(c.get('price'))
                    if p <= 0:
                        continue
                    rel = abs(p - float(level_price)) / p
                    if rel <= 0.002:
                        if best is None or float(c.get('strength', 0)) > float(best.get('strength', 0)):
                            best = c
                except Exception:
                    continue
            if best and best.get('source'):
                src = str(best.get('source'))
                if src.startswith('swing_'):
                    return src.replace('swing_', 'struct_')
                return src
        except Exception:
            return "-"
        return "-"

    def _safe_plan(self, plan: dict) -> tuple[dict, str, List[str]]:
        """Validate plan deterministically for report display; fallback to baseline if invalid."""
        reasons: List[str] = []
        if not isinstance(plan, dict):
            return ({'ladder_weights_pct': {'S1': 15, 'S2': 25, 'S3': 35}, 'reserve_pct': 25, 'strategy_source': 'baseline_fallback'}, 'baseline_fallback', ["Invalid plan format; fallback to baseline."])

        weights = plan.get('ladder_weights_pct')
        reserve = plan.get('reserve_pct')
        src = plan.get('strategy_source') or 'baseline'

        try:
            if not isinstance(weights, dict):
                raise ValueError('weights_not_dict')
            if set(weights.keys()) != {'S1', 'S2', 'S3'}:
                raise ValueError('missing_keys')
            s1 = int(weights.get('S1'))
            s2 = int(weights.get('S2'))
            s3 = int(weights.get('S3'))
            reserve_i = int(reserve)
            if reserve_i < 25:
                raise ValueError('reserve_lt_25')
            if (s1 + s2 + s3 + reserve_i) != 100:
                raise ValueError('sum_not_100')
            if not (s1 <= s2 <= s3):
                raise ValueError('not_monotonic')
            normalized = {
                'ladder_weights_pct': {'S1': s1, 'S2': s2, 'S3': s3},
                'reserve_pct': reserve_i,
                'budget_multiplier': plan.get('budget_multiplier'),
                'strategy_source': src,
            }
            return normalized, src, reasons
        except Exception as e:
            reasons.append(f"Plan invalid ({str(e)}); fallback to baseline.")
            fallback = {
                'ladder_weights_pct': {'S1': 15, 'S2': 25, 'S3': 35},
                'reserve_pct': 25,
                'budget_multiplier': plan.get('budget_multiplier'),
                'strategy_source': 'baseline_fallback',
            }
            return fallback, 'baseline_fallback', reasons

    def _deterministic_reasons(self, item: Dict) -> List[str]:
        reasons: List[str] = []
        score = float(item.get('score') or 0)
        rank = item.get('rank')
        action = item.get('action', 'hold')

        if rank is not None:
            reasons.append(f"Rank(5y)={float(rank):.2f}，Score={score:.1f}。")
        else:
            reasons.append(f"Score={score:.1f}。")

        if score >= float(CHEAP_THRESHOLD):
            reasons.append("分数达到阈值，允许使用“便宜/低估/吸筹”等措辞。")
        else:
            reasons.append("排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。")

        price = item.get('price')
        s1 = item.get('s1')
        if price and s1:
            dist_pct = (float(s1) / float(price)) - 1
            reasons.append(f"距离 S1 约 {dist_pct:.1%}。")

        reasons.append(f"Action={action}；reserve={item.get('reserve_pct', '-') }%。")
        return reasons

    def _deterministic_market_overview(self, market_regime: str, market_multiplier: float, top_stocks: List[Dict]) -> str:
        top_symbols = [x['symbol'] for x in top_stocks[:3]]
        return (
            f"市场状态：{market_regime}，风险乘数 {market_multiplier:.1f}。"
            f"今日 Top Rank 名单：{', '.join(top_symbols) if top_symbols else 'N/A'}。"
        )

    def _deterministic_execution_notes(self, market_regime: str) -> List[str]:
        notes = []
        notes.append(f"按市场状态执行：{market_regime}。")
        notes.append("遵循分批、保留充足 reserve 的纪律，避免一次性打光子弹。")
        notes.append("仅基于确定性指标与已校验策略展示，不使用 LLM 自由发挥文案。")
        return notes

    def generate_report(self, date_str: str, symbols: List[str]):
        logger.info(f"Generating daily report for {date_str}")
        
        market, recos, feats, levels = self.get_data_for_date(date_str)
        
        if not market:
            logger.warning("No market state found, using defaults")
            market_regime = "Unknown"
            market_multiplier = 1.0
        else:
            market_regime = market.regime
            market_multiplier = market.multiplier
            
        # Organize data by symbol
        data_by_symbol = {}
        for s in symbols:
            data_by_symbol[s] = {'symbol': s}
            
        for f in feats:
            if f.symbol in data_by_symbol:
                data_by_symbol[f.symbol]['score'] = f.deepvalue_score_smooth
                data_by_symbol[f.symbol]['rank'] = f.pct_rank_5y
                data_by_symbol[f.symbol]['price'] = f.price_used
                
        for l in levels:
            if l.symbol in data_by_symbol:
                data_by_symbol[l.symbol]['s1'] = l.s1
                data_by_symbol[l.symbol]['s2'] = l.s2
                data_by_symbol[l.symbol]['s3'] = l.s3
                data_by_symbol[l.symbol]['s_meta'] = l.s_meta
                
        for r in recos:
            if r.symbol in data_by_symbol:
                data_by_symbol[r.symbol]['action'] = r.action
                data_by_symbol[r.symbol]['plan'] = json.loads(r.plan_json)
                data_by_symbol[r.symbol]['explain'] = json.loads(r.explain_json)

        for v in data_by_symbol.values():
            plan, strategy_source, plan_notes = self._safe_plan(v.get('plan', {}))
            v['plan'] = plan
            v['strategy_source'] = strategy_source
            v['reserve_pct'] = plan.get('reserve_pct')

            s_meta = v.get('s_meta')
            v['s1_source'] = self._maybe_override_source_with_pp(s_meta, 's1', v.get('s1'), self._parse_level_source(s_meta, v.get('s1')))
            v['s2_source'] = self._maybe_override_source_with_pp(s_meta, 's2', v.get('s2'), self._parse_level_source(s_meta, v.get('s2')))
            v['s3_source'] = self._parse_level_source(s_meta, v.get('s3'))

            pp_status, pp_band = self._parse_pp_info(s_meta)
            v['pp_status'] = pp_status
            v['pp_band'] = pp_band

            if plan_notes:
                v['plan_notes'] = plan_notes
                
        # Filter valid
        valid_data = [v for v in data_by_symbol.values() if 'score' in v]
        
        sorted_by_score = sorted(valid_data, key=lambda x: x.get('score', 0), reverse=True)
        top_items = sorted_by_score[:3]
        market_overview = self._deterministic_market_overview(market_regime, market_multiplier, top_items)
        execution_notes = self._deterministic_execution_notes(market_regime)
        risk_warning = "本报告基于确定性规则生成，仅作参考，不构成投资建议。请自行评估风险与合规要求。"
        
        # 2. Render Markdown
        table_md = self._format_table(valid_data)
        
        md = f"""# DeepValue Daily Report - {date_str}

## 1. Market Overview
**Regime**: {market_regime}
**Multiplier**: {market_multiplier:.2f}x

{market_overview}

## 2. DeepValue Rankings
{table_md}

## 3. Execution Notes
{chr(10).join(['- ' + note for note in execution_notes])}

## 4. Watchlist Details
"""
        
        for item in sorted_by_score:
            s = item['symbol']
            action = item.get('action', 'N/A')
            plan = item.get('plan', {})
            weights = plan.get('ladder_weights_pct', {})
            reserve_pct = item.get('reserve_pct')
            strategy_source = item.get('strategy_source', '-')

            md += f"\n### {s} ({item.get('score', 0):.0f})\n"
            md += f"**Action**: {action}\n"
            md += f"**Price**: {item.get('price', 0):.2f}\n"
            md += f"- **strategy_source**: {strategy_source}\n"
            md += f"- **reserve_pct**: {reserve_pct if reserve_pct is not None else '-'}%\n"

            if item.get('pp_status') and item.get('pp_status') != '-':
                md += f"- **pp_status**: {item.get('pp_status')}\n"
            if item.get('pp_band') and item.get('pp_band') != '-':
                md += f"- **pp_band**: {item.get('pp_band')}\n"
            
            # Show Ladder
            if item.get('s1'):
                md += f"- **S1**: {item['s1']:.2f} ({weights.get('S1', 0)}%) [{item.get('s1_source', '-')}]\n"
            if item.get('s2'):
                md += f"- **S2**: {item['s2']:.2f} ({weights.get('S2', 0)}%) [{item.get('s2_source', '-')}]\n"
            if item.get('s3'):
                md += f"- **S3**: {item['s3']:.2f} ({weights.get('S3', 0)}%) [{item.get('s3_source', '-')}]\n"
                
            reasons = self._deterministic_reasons(item)
            if item.get('plan_notes'):
                reasons = list(item.get('plan_notes')) + reasons
            
            if reasons:
                md += "**Reasons**:\n"
                for r in reasons:
                    md += f"- {r}\n"
                    
        md += f"\n## 5. Risk Warning\n{risk_warning}\n"
        
        # Save Report
        self.save_report(date_str, md, symbols)
        return md

    def save_report(self, date_str: str, content: str, symbols: List[str]):
        meta = {'symbols': symbols}
        
        report_id = f"daily_{date_str}"
        record = {
            'report_id': report_id,
            'date': date_str,
            'type': 'daily',
            'content_md': content,
            'meta_json': json.dumps(meta),
            'created_at': datetime.utcnow().isoformat()
        }
        
        stmt = insert(Report).values(record)
        stmt = stmt.on_conflict_do_update(
            index_elements=['report_id'],
            set_={
                'content_md': stmt.excluded.content_md,
                'meta_json': stmt.excluded.meta_json,
                'created_at': stmt.excluded.created_at
            }
        )
        self.db.execute(stmt)
        self.db.commit()
        logger.info(f"Saved daily report {report_id}")

if __name__ == "__main__":
    from src.config.settings import UNIVERSE
    from src.data.ingestion import DataIngestion # Just to make sure we have data? No.
    
    # Simple test run assuming data exists
    store = DataStore()
    llm = LLMService(store)
    gen = DailyReportGenerator(store, llm)
    
    # Use today or latest available date
    # Let's find latest date in prices
    session = store.get_session()
    latest_date = session.execute(select(PriceDaily.date).order_by(PriceDaily.date.desc()).limit(1)).scalar_one_or_none()
    
    if latest_date:
        gen.generate_report(latest_date, UNIVERSE)
    else:
        logger.warning("No data found to generate report")
