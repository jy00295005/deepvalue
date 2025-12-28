from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Literal, Optional

class LadderStep(BaseModel):
    tier: Literal["S1", "S2", "S3"]
    weight_pct: int

class StrategyOutput(BaseModel):
    symbol: str
    action: Literal["accumulate", "hold", "pause_shallow"]
    ladder_weights_pct: dict[str, int] # e.g. {"S1": 15, ...}
    reserve_pct: int
    avoid_chasing: bool
    reasons: List[str]
    confidence: float

    @field_validator('ladder_weights_pct')
    def validate_weights(cls, v):
        required = {"S1", "S2", "S3"}
        if set(v.keys()) != required:
            raise ValueError("Keys must be exactly S1, S2, S3")

        s1 = int(v.get("S1"))
        s2 = int(v.get("S2"))
        s3 = int(v.get("S3"))

        if any(x < 0 or x > 100 for x in [s1, s2, s3]):
            raise ValueError("Each ladder weight must be 0..100")

        if not (s1 <= s2 <= s3):
            raise ValueError("Must satisfy S1 <= S2 <= S3")

        total = s1 + s2 + s3
        if not (0 <= total <= 100):
            raise ValueError("Sum of ladder weights must be 0..100")

        return {"S1": s1, "S2": s2, "S3": s3}

    @field_validator('reserve_pct')
    def validate_reserve(cls, v):
        if v < 25:
            raise ValueError("Reserve must be at least 25%")
        if v > 100:
            raise ValueError("Reserve must be 0..100")
        return v

    @field_validator('confidence')
    def validate_confidence(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Confidence must be 0..1")
        return v

    @field_validator('action')
    def validate_action(cls, v):
        return v

    @model_validator(mode='after')
    def validate_total_100(self):
        w = self.ladder_weights_pct
        total = int(w.get('S1', 0)) + int(w.get('S2', 0)) + int(w.get('S3', 0)) + int(self.reserve_pct)
        if total != 100:
            raise ValueError("Must satisfy S1+S2+S3+reserve == 100")
        return self

class ReportOutput(BaseModel):
    summary_paragraph: str
    execution_notes: List[str]
    risk_warning: str

class StrategyBatchOutput(BaseModel):
    strategies: List[StrategyOutput]
