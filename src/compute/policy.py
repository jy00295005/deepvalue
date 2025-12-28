import pandas as pd
import numpy as np
import json
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from loguru import logger

from src.data.store import DataStore, PriceDaily, FeatureDaily, LevelDaily, MarketStateDaily, RecommendationDaily
from src.config.settings import (
    MARKET_PROXY_SYMBOL,
    BUDGET_PER_SYMBOL_USD,
    LADDER_DEFAULT_WEIGHTS_PCT,
    RESERVE_PCT,
    BUFFER_PCT,
    REGIME_MULTIPLIERS,
    ACCUMULATE_SCORE_MIN
)

class PolicyEngine:
    def __init__(self, store: DataStore):
        self.store = store
        self.db = store.get_session()

    def get_latest_data(self, symbol: str):
        # 1. Price
        price = self.db.execute(
            select(PriceDaily).where(PriceDaily.symbol == symbol).order_by(PriceDaily.date.desc()).limit(1)
        ).scalar_one_or_none()
        
        # 2. Features
        feature = self.db.execute(
            select(FeatureDaily).where(FeatureDaily.symbol == symbol).order_by(FeatureDaily.date.desc()).limit(1)
        ).scalar_one_or_none()
        
        # 3. Levels
        levels = self.db.execute(
            select(LevelDaily).where(LevelDaily.symbol == symbol).order_by(LevelDaily.date.desc()).limit(1)
        ).scalar_one_or_none()
        
        return price, feature, levels

    def get_market_state(self, date_str: str):
        # Find state for this date or latest before it
        state = self.db.execute(
            select(MarketStateDaily).where(MarketStateDaily.date <= date_str).order_by(MarketStateDaily.date.desc()).limit(1)
        ).scalar_one_or_none()
        return state

    def compute_distances(self, price: float, levels: LevelDaily):
        dists = {}
        if not levels:
            return {}
            
        for name in ['s1', 's2', 's3', 'r1', 'r2', 'r3']:
            lvl_val = getattr(levels, name)
            if lvl_val is not None:
                # Distance % = (Level / Price) - 1
                # If Level < Price (Support), result is negative (e.g. 0.9/1.0 - 1 = -0.1)
                # If Level > Price (Resistance), result is positive
                pct = (lvl_val / price) - 1
                dists[name + '_pct'] = pct
                dists[name + '_usd'] = lvl_val - price
            else:
                dists[name + '_pct'] = None
                dists[name + '_usd'] = None
        return dists

    def generate_baseline(self, symbol: str):
        price_row, feature_row, level_row = self.get_latest_data(symbol)
        
        if not price_row:
            logger.warning(f"No price data for {symbol}")
            return

        date_str = price_row.date
        market_state = self.get_market_state(date_str)
        
        # Default Market State if missing
        if not market_state:
            regime = 'neutral'
            multiplier = 0.9
        else:
            regime = market_state.regime
            multiplier = market_state.multiplier

        # Canonical Price
        # Policy should use the same price as Features/Levels
        # If we just loaded PriceDaily, we need to handle adj_close
        current_price = price_row.adj_close if price_row.adj_close else price_row.close
        
        # Compute Distances
        dists = self.compute_distances(current_price, level_row)
        
        # Determine Action (Baseline)
        # Rule: 
        # If any S level is within BUFFER_PCT, action = accumulate
        # Else if Risk-off, action = pause_shallow (conservative)
        # Else action = hold (wait for setup)
        
        action = "hold"
        is_near_support = False
        
        if level_row:
            for s in ['s1', 's2', 's3']:
                s_val = getattr(level_row, s)
                if s_val:
                    # Check if Price <= S * (1 + buffer)
                    # Actually, usually we buy when price drops TO the level.
                    # So Price <= Level + buffer_amt
                    # Or Price/Level - 1 <= Buffer ?
                    # If Price is 101, Level is 100. Dist% = -1% (No wait, Level/Price - 1 = 100/101 - 1 = -0.0099)
                    # Let's stick to simple: abs(Price - Level)/Price < Buffer ?
                    # Or simpler: Is Price close enough?
                    # If Price > Level, but close: (Price - Level)/Level < Buffer
                    if current_price > s_val:
                        dist_to_s = (current_price - s_val) / s_val
                        if dist_to_s < BUFFER_PCT:
                            is_near_support = True
                    else:
                        # Price is below support (penetrated)
                        is_near_support = True

        if is_near_support:
            action = "accumulate"
        elif regime == 'risk_off':
            action = "pause_shallow"

        score_val = feature_row.deepvalue_score_smooth if feature_row else None
        if action == "accumulate" and score_val is not None and float(score_val) < float(ACCUMULATE_SCORE_MIN):
            action = "hold"
        
        # Construct Plans
        # Weights are fixed percentages for Baseline
        # But we need to record them
        
        plan = {
            'ladder_weights_pct': LADDER_DEFAULT_WEIGHTS_PCT,
            'reserve_pct': RESERVE_PCT,
            'budget_multiplier': multiplier,
            'strategy_source': 'baseline'
        }
        
        constraints = {
            'budget_per_symbol_usd': BUDGET_PER_SYMBOL_USD,
            'effective_budget_usd': BUDGET_PER_SYMBOL_USD * multiplier,
            'regime': regime
        }
        
        # Explanation (Deterministic)
        explain = {
            'reasons': [f"Baseline: {action}. Regime: {regime}. Near Support: {is_near_support}"],
            'confidence': 1.0,
            'strategy_source': 'baseline',
            'score': feature_row.deepvalue_score_smooth if feature_row else None
        }
        
        # Save Recommendation
        record = {
            'symbol': symbol,
            'date': date_str,
            'action': action,
            'plan_json': json.dumps(plan),
            'constraints_json': json.dumps(constraints),
            'explain_json': json.dumps(explain),
            'llm_used': 0
        }
        
        stmt = insert(RecommendationDaily).values(record)
        stmt = stmt.on_conflict_do_update(
            index_elements=['symbol', 'date'],
            set_={
                'action': stmt.excluded.action,
                'plan_json': stmt.excluded.plan_json,
                'constraints_json': stmt.excluded.constraints_json,
                'explain_json': stmt.excluded.explain_json,
                'llm_used': stmt.excluded.llm_used
            }
        )
        self.db.execute(stmt)
        self.db.commit()
        logger.info(f"Saved baseline recommendation for {symbol} on {date_str}")

    def run(self, symbols: list[str]):
        logger.info(f"Generating baseline policies for {len(symbols)} symbols")
        for symbol in symbols:
            try:
                self.generate_baseline(symbol)
            except Exception as e:
                logger.error(f"Error generating baseline for {symbol}: {e}")

if __name__ == "__main__":
    from src.config.settings import UNIVERSE
    store = DataStore()
    engine = PolicyEngine(store)
    engine.run(UNIVERSE)
