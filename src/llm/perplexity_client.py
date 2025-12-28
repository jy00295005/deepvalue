"""
Perplexity API client for external support level extraction.

This module provides an independent decision source for support levels,
querying Perplexity's web search to extract technical support zones from
public sources without requiring local historical data.
"""

import os
import re
import json
from typing import Optional
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

try:
    from perplexity import Perplexity
except ImportError:
    Perplexity = None  # Will fail gracefully if not installed

from src.config.settings import MAG7_SYMBOLS


BASE_DIR = Path(__file__).resolve().parent.parent.parent
PP_SUPPORTS_DIR = BASE_DIR / "data" / "external" / "perplexity_supports"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SupportBand:
    """Parsed support band from Perplexity output."""
    ticker: str
    low: Optional[float] = None
    high: Optional[float] = None
    mid: Optional[float] = None
    last_price: Optional[float] = None
    width_pct: Optional[float] = None
    dist_pct: Optional[float] = None
    confidence: float = 0.0
    evidence_type: str = "unknown"
    notes: str = ""
    missing_data: bool = True
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Prompt templates (optimized to reduce hallucination)
# ---------------------------------------------------------------------------

PERPLEXITY_SYSTEM_PROMPT = """You are a financial data extractor. Your job is to EXTRACT support levels from web sources.

Rules:
1. Prefer explicit support levels mentioned in sources (e.g., TradingView ideas, analyst reports, options open interest, technical articles).
2. If explicit support is not available, you MAY provide a commonly-referenced support zone (e.g., major round number, widely watched prior low) ONLY if you label it as derived_level and set confidence <= 0.40.
3. Never fabricate citations. If evidence is weak, lower confidence and explain in notes.
4. Output valid JSON only, no markdown code blocks."""

def get_perplexity_user_prompt(tickers: list[str]) -> str:
    ticker_str = ", ".join(tickers)
    return f"""Extract the current strongest support levels for these tickers: {ticker_str}

Requirements:
- Search for technical analysis, chart analysis, or analyst support targets from the last 2 months.
- Report support as a PRICE RANGE (low-high) if available.
- Include a secondary support (support_alt) if mentioned.
- For each ticker, also report:
  - confidence: 0.0-1.0 (how reliable is the source? 1.0 = explicit technical level, 0.5 = analyst target, 0.2 = weak/derived)
  - evidence_type: "technical_level" | "analyst_target" | "options_data" | "derived_level" | "unknown"
- If you cannot find any reasonable support zone from sources, set missing_data=true.

Output JSON array (no code blocks):
[
  {{
    "ticker": "AAPL",
    "as_of_date": "2025-12-27",
    "last_price": 172.50,
    "support_main": "$165 - $170",
    "support_alt": "$155 - $160",
    "confidence": 0.8,
    "evidence_type": "technical_level",
    "missing_data": false,
    "notes": "Support from TradingView analysis..."
  }},
  ...
]"""


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------

def _compute_confidence(band: SupportBand) -> float:
    """
    Compute final confidence score for a support band.
    
    Factors:
    - Base: from PP's self-reported confidence (if any)
    - Width penalty: wider bands = more uncertainty
    - Notes penalty: "estimated/inferred/no specific" = lower confidence
    - Direction check: support must be below last_price
    """
    # Missing data = 0
    if band.missing_data or band.low is None or band.high is None or band.last_price is None:
        return 0.0
    
    # Direction check: support should be below price
    if band.mid and band.mid >= band.last_price:
        return 0.0
    
    # Start with PP's self-reported confidence or default 0.6
    base = band.raw.get("confidence", 0.6)
    if not isinstance(base, (int, float)):
        base = 0.6
    base = max(0.0, min(1.0, float(base)))
    
    # Width penalty
    width_factor = 1.0
    if band.width_pct is not None:
        if band.width_pct <= 0.03:
            width_factor = 1.0
        elif band.width_pct <= 0.08:
            width_factor = 0.7
        else:
            width_factor = 0.4
    
    # Notes penalty (check for estimation/inference language)
    notes_factor = 1.0
    notes_lower = band.notes.lower()
    penalty_phrases = [
        "estimated", "inferred", "no specific", "structure", 
        "no support", "unknown", "guessed", "approximate"
    ]
    if any(phrase in notes_lower for phrase in penalty_phrases):
        notes_factor = 0.5
    
    # Evidence type boost/penalty
    evidence_factor = 1.0
    ev = band.evidence_type.lower()
    if ev == "technical_level":
        evidence_factor = 1.0
    elif ev == "analyst_target":
        evidence_factor = 0.85
    elif ev == "options_data":
        evidence_factor = 0.9
    elif ev == "derived_level":
        evidence_factor = 0.55
    else:
        evidence_factor = 0.6
    
    final = base * width_factor * notes_factor * evidence_factor
    return max(0.0, min(1.0, final))


def _parse_price_range(range_str: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """Parse '$230 - $250' into (230.0, 250.0)."""
    if not range_str:
        return None, None
    
    # Remove $ and commas, find numbers
    cleaned = range_str.replace("$", "").replace(",", "")
    numbers = re.findall(r"[\d.]+", cleaned)
    
    if len(numbers) >= 2:
        try:
            return float(numbers[0]), float(numbers[1])
        except ValueError:
            return None, None
    elif len(numbers) == 1:
        try:
            val = float(numbers[0])
            return val, val  # Single point as degenerate band
        except ValueError:
            return None, None
    return None, None


def _parse_single_result(item: dict) -> SupportBand:
    """Parse a single ticker result from PP output into SupportBand."""
    ticker = item.get("ticker", "UNKNOWN")
    last_price = item.get("last_price")
    missing = item.get("missing_data", False)
    
    # Handle null/None last_price
    if last_price is None or missing:
        return SupportBand(
            ticker=ticker,
            missing_data=True,
            notes=item.get("notes", ""),
            raw=item
        )
    
    try:
        last_price = float(last_price)
    except (ValueError, TypeError):
        return SupportBand(ticker=ticker, missing_data=True, raw=item)
    
    # Parse main support band
    low, high = _parse_price_range(item.get("support_main"))
    
    if low is None or high is None:
        return SupportBand(
            ticker=ticker,
            last_price=last_price,
            missing_data=True,
            notes=item.get("notes", ""),
            raw=item
        )
    
    mid = (low + high) / 2
    width_pct = (high - low) / last_price if last_price > 0 else None
    dist_pct = (last_price - mid) / last_price if last_price > 0 else None
    
    band = SupportBand(
        ticker=ticker,
        low=low,
        high=high,
        mid=mid,
        last_price=last_price,
        width_pct=width_pct,
        dist_pct=dist_pct,
        evidence_type=item.get("evidence_type", "unknown"),
        notes=item.get("notes", ""),
        missing_data=False,
        raw=item
    )
    
    # Compute confidence
    band.confidence = _compute_confidence(band)
    
    return band


# ---------------------------------------------------------------------------
# Client class
# ---------------------------------------------------------------------------

class PerplexityClient:
    """Client for fetching external support levels from Perplexity."""
    
    def __init__(self):
        self.api_key = os.getenv("PERPLEXITY_API_KEY")
        self.client = None
        
        # By default we do NOT call Perplexity API (manual snapshot mode).
        # If you want to enable API calls again, set PERPLEXITY_ENABLE_API=1.
        enable_api = os.getenv("PERPLEXITY_ENABLE_API") == "1"

        if enable_api:
            if not self.api_key:
                logger.warning("PERPLEXITY_API_KEY not set. External support levels disabled.")
            elif Perplexity is None:
                logger.warning("perplexity package not installed. Run: pip install perplexity")
            else:
                self.client = Perplexity()
    
    def is_available(self) -> bool:
        """Check if Perplexity API client is properly configured (only if enabled)."""
        return self.client is not None and self.api_key is not None

    def load_manual_snapshot(self, as_of_date: str) -> dict:
        """Load manual Perplexity snapshot JSON from data/external/perplexity_supports."""
        path = PP_SUPPORTS_DIR / f"pp_supports_{as_of_date}.json"
        if not path.exists():
            # Optional: fallback to latest
            latest = PP_SUPPORTS_DIR / "pp_supports_latest.json"
            if latest.exists():
                path = latest
            else:
                raise FileNotFoundError(f"PP snapshot not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _manual_to_bands(self, snapshot: dict, tickers: list[str]) -> dict[str, SupportBand]:
        """Convert manual snapshot schema to SupportBand map (use best short_term support as main band)."""
        out: dict[str, SupportBand] = {}
        symbols = snapshot.get("symbols") if isinstance(snapshot, dict) else None
        if not isinstance(symbols, dict):
            raise ValueError("Invalid snapshot format: missing symbols")

        for t in tickers:
            data = symbols.get(t)
            if not isinstance(data, dict):
                out[t] = SupportBand(ticker=t, missing_data=True, notes="missing_in_snapshot")
                continue

            approx_price = data.get("approx_price")
            supports = data.get("supports")
            missing_reason = data.get("missing_reason")
            if not supports or not isinstance(supports, list):
                note = missing_reason or "supports_empty"
                out[t] = SupportBand(ticker=t, missing_data=True, notes=str(note), raw=data)
                continue

            # Pick the best S1 candidate: prefer short_term, higher confidence, and closest below approx_price if available
            def _support_mid(s: dict) -> Optional[float]:
                if s.get("kind") == "level":
                    v = s.get("value")
                    return float(v) if isinstance(v, (int, float)) else None
                if s.get("kind") == "range":
                    lo = s.get("low")
                    hi = s.get("high")
                    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                        return (float(lo) + float(hi)) / 2
                return None

            def _sort_key(s: dict):
                horizon = s.get("horizon")
                horizon_rank = 0 if horizon == "short_term" else (1 if horizon == "medium_term" else 2)
                conf = s.get("confidence")
                conf_f = float(conf) if isinstance(conf, (int, float)) else 0.0
                mid = _support_mid(s)
                # Distance: prefer closer (smaller drop) if approx_price available
                if isinstance(approx_price, (int, float)) and mid is not None and float(approx_price) > 0:
                    drop = (float(approx_price) - mid) / float(approx_price)
                else:
                    drop = 0.0
                return (horizon_rank, -conf_f, drop)

            candidates = [s for s in supports if isinstance(s, dict)]
            candidates.sort(key=_sort_key)
            best = candidates[0] if candidates else None

            if not best:
                out[t] = SupportBand(ticker=t, missing_data=True, notes="no_valid_supports", raw=data)
                continue

            mid = _support_mid(best)
            if mid is None:
                out[t] = SupportBand(ticker=t, missing_data=True, notes="best_missing_mid", raw=data)
                continue

            # Build a pseudo band: for level use +/-0, for range use low/high
            if best.get("kind") == "range":
                low = float(best.get("low"))
                high = float(best.get("high"))
            else:
                low = float(mid)
                high = float(mid)

            last_price = float(approx_price) if isinstance(approx_price, (int, float)) else None
            width_pct = (high - low) / last_price if last_price and last_price > 0 else None
            dist_pct = (last_price - mid) / last_price if last_price and last_price > 0 else None

            band = SupportBand(
                ticker=t,
                low=low,
                high=high,
                mid=float(mid),
                last_price=last_price,
                width_pct=width_pct,
                dist_pct=dist_pct,
                evidence_type=str(best.get("evidence_type") or "unknown"),
                notes=str(best.get("note") or ""),
                missing_data=False,
                raw={"confidence": best.get("confidence"), **best},
            )
            band.confidence = _compute_confidence(band)
            out[t] = band

        return out
    
    def fetch_support_levels(self, tickers: Optional[list[str]] = None, as_of_date: Optional[str] = None) -> dict[str, SupportBand]:
        """
        Fetch support levels for given tickers from Perplexity.
        
        Args:
            tickers: List of ticker symbols. Defaults to MAG7_SYMBOLS.
        
        Returns:
            Dict mapping ticker -> SupportBand
        """
        if tickers is None:
            tickers = [t for t in MAG7_SYMBOLS if t != "GOOGL"]  # Avoid duplicate GOOG/GOOGL
        
        result: dict[str, SupportBand] = {}
        
        # Manual snapshot mode (default)
        if as_of_date:
            try:
                snapshot = self.load_manual_snapshot(as_of_date)
                return self._manual_to_bands(snapshot, tickers)
            except Exception as e:
                logger.warning(f"Failed to load manual PP snapshot for {as_of_date}: {e}")
                for t in tickers:
                    result[t] = SupportBand(ticker=t, missing_data=True, notes="pp_snapshot_missing_or_invalid")
                return result

        # If no as_of_date provided, do not call API; return missing
        for t in tickers:
            result[t] = SupportBand(ticker=t, missing_data=True, notes="pp_snapshot_date_required")
        return result
        
        try:
            user_prompt = get_perplexity_user_prompt(tickers)
            
            completion = self.client.chat.completions.create(
                model="sonar",
                messages=[
                    {"role": "system", "content": PERPLEXITY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                web_search_options={"search_context_size": "medium"},
                temperature=0.1,
            )
            
            raw_content = completion.choices[0].message.content
            logger.debug(f"Perplexity raw response: {raw_content[:500]}...")
            
            # Parse JSON from response (handle potential markdown code blocks)
            json_str = raw_content
            if "```" in json_str:
                # Extract JSON from code block
                match = re.search(r"```(?:json)?\s*([\s\S]*?)```", json_str)
                if match:
                    json_str = match.group(1)
            
            parsed = json.loads(json_str.strip())
            
            if isinstance(parsed, list):
                for item in parsed:
                    band = _parse_single_result(item)
                    result[band.ticker] = band
            else:
                logger.warning("Perplexity response is not a list")
        
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Perplexity JSON: {e}")
        except Exception as e:
            logger.warning(f"Perplexity API call failed: {e}")
        
        # Ensure all requested tickers have an entry
        for t in tickers:
            if t not in result:
                result[t] = SupportBand(ticker=t, missing_data=True, notes="not_in_response")
        
        return result


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def fetch_external_supports(tickers: Optional[list[str]] = None) -> dict[str, SupportBand]:
    """Convenience function to fetch external support levels.

    Manual snapshot mode requires a date; this helper is kept for backward-compat.
    """
    client = PerplexityClient()
    return client.fetch_support_levels(tickers)


def fetch_external_supports_for_date(as_of_date: str, tickers: Optional[list[str]] = None) -> dict[str, SupportBand]:
    """Fetch external support levels for a given date from manual snapshot JSON."""
    client = PerplexityClient()
    return client.fetch_support_levels(tickers, as_of_date=as_of_date)
