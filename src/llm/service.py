import json
from loguru import logger
from typing import Optional, List

from src.data.store import DataStore, RecommendationDaily
from src.llm.client import LLMClient
from src.llm.prompts import (
    STRATEGY_SYSTEM_PROMPT,
    STRATEGY_BATCH_SYSTEM_PROMPT,
    REPORT_SYSTEM_PROMPT,
    get_strategy_user_prompt,
    get_strategy_batch_user_prompt,
    get_report_user_prompt,
)
from src.llm.validator import StrategyOutput, StrategyBatchOutput, ReportOutput

class LLMService:
    def __init__(self, store: DataStore):
        self.store = store
        self.client = LLMClient(store)
        self.db = store.get_session()

    def generate_strategy(self, 
                          symbol: str, 
                          deterministic_data: dict, 
                          baseline_plan: dict) -> dict:
        """
        Orchestrates Strategy generation:
        1. Construct Input
        2. Call LLM
        3. Validate
        4. Fallback if needed
        """
        
        # 1. Prepare Prompt Input
        # We need to flatten deterministic_data for the prompt
        # deterministic_data should contain: symbol, price, score, levels, distances, market_state, baseline_action
        
        user_prompt = get_strategy_user_prompt(deterministic_data)
        
        # 2. Call LLM
        try:
            raw_response = self.client.call_completion(
                role="strategy",
                system_prompt=STRATEGY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                input_data=deterministic_data,
                prompt_version="v2"
            )
        except Exception as e:
            logger.error(f"LLM Call error for {symbol}: {e}")
            raw_response = None

        if not raw_response:
            logger.warning(f"Using baseline for {symbol} (LLM failed)")
            return self._use_baseline(symbol, baseline_plan, "llm_failed")

        # 3. Validate
        try:
            validated = StrategyOutput(**raw_response)
            
            # Check price consistency if LLM returned prices (we asked for weights only in schema, but prompt might hallucinate)
            # Our validator schema `StrategyOutput` strictly checks weights and reserve.
            # We assume LLM output matches schema structure.
            
            # Extra check: Symbol match
            if validated.symbol != symbol:
                raise ValueError(f"Symbol mismatch: {validated.symbol} != {symbol}")

            # Return validated dict
            result = validated.model_dump()
            result['source'] = 'llm'
            result['strategy_source'] = 'llm'
            return result

        except Exception as e:
            logger.info(f"Validation failed for {symbol}: {e}. Falling back to baseline.")
            return self._use_baseline(symbol, baseline_plan, f"validation_error: {str(e)}")

    def generate_strategies_batch(self, items: list[dict], baseline_by_symbol: dict[str, dict]) -> dict[str, dict]:
        """Generate strategies for multiple symbols in one call.

        Returns mapping symbol -> strategy dict. Missing/invalid symbols fall back to baseline_fallback.
        """
        if not items:
            return {}

        user_prompt = get_strategy_batch_user_prompt(items)
        input_data = {"strategies_input": items}

        try:
            raw_response = self.client.call_completion(
                role="strategy_batch",
                system_prompt=STRATEGY_BATCH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                input_data=input_data,
                prompt_version="v1"
            )
        except Exception as e:
            # If the single batch call fails, fallback all
            out: dict[str, dict] = {}
            for it in items:
                sym = it.get('symbol')
                out[sym] = self._use_baseline(sym, baseline_by_symbol.get(sym, {}), f"batch_llm_failed: {e}")
            return out

        out: dict[str, dict] = {}
        if not raw_response:
            for it in items:
                sym = it.get('symbol')
                out[sym] = self._use_baseline(sym, baseline_by_symbol.get(sym, {}), "batch_llm_failed")
            return out

        try:
            validated_batch = StrategyBatchOutput(**raw_response)
            for st in validated_batch.strategies:
                result = st.model_dump()
                result['source'] = 'llm'
                result['strategy_source'] = 'llm'
                out[result['symbol']] = result
        except Exception as e:
            # If batch wrapper fails, try to salvage list-like payloads
            self._db_safe_log_info(f"Batch validation failed: {e}")

        # Ensure every requested symbol is present
        for it in items:
            sym = it.get('symbol')
            if sym not in out:
                out[sym] = self._use_baseline(sym, baseline_by_symbol.get(sym, {}), "batch_missing_or_invalid")

        return out

    def _db_safe_log_info(self, msg: str):
        logger.info(msg)

    def _use_baseline(self, symbol: str, baseline_plan: dict, reason: str) -> dict:
        # Construct a response that mimics LLM output but uses baseline values
        return {
            "symbol": symbol,
            "action": baseline_plan.get('action', 'hold'),
            "ladder_weights_pct": baseline_plan.get('plan_json', {}).get('ladder_weights_pct', {"S1": 15, "S2": 25, "S3": 35}),
            "reserve_pct": baseline_plan.get('plan_json', {}).get('reserve_pct', 25),
            "avoid_chasing": False,
            "reasons": [f"Baseline fallback: {reason}"],
            "confidence": 1.0,
            "source": "baseline_fallback",
            "strategy_source": "baseline_fallback"
        }

    def generate_report_content(self, report_input: dict) -> dict:
        user_prompt = get_report_user_prompt(report_input)
        
        try:
            raw_response = self.client.call_completion(
                role="report",
                system_prompt=REPORT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                input_data=report_input,
                prompt_version="v1"
            )
        except Exception as e:
            logger.error(f"LLM Call error for report: {e}")
            raw_response = None
            
        if not raw_response:
            return self._report_fallback()
            
        try:
            validated = ReportOutput(**raw_response)
            return validated.model_dump()
        except Exception as e:
            logger.warning(f"Report validation failed: {e}")
            return self._report_fallback()

    def _report_fallback(self) -> dict:
        return {
            "summary_paragraph": "自动生成失败，使用模板回退。",
            "execution_notes": ["请参考下表中的确定性指标。"],
            "risk_warning": "数据仅供参考，请注意风险。"
        }
