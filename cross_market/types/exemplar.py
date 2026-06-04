"""Exemplar model for few-shot LLM prompting from verified outcomes."""
from pydantic import BaseModel
from typing import Optional


class Exemplar(BaseModel):
    snapshot: dict
    gold_assessment: dict  # LLMAssessment as dict
    pattern: str
    outcome_30s: Optional[float] = None  # price change
    outcome_60s: Optional[float] = None
    was_correct: Optional[bool] = None
    session_date: Optional[str] = None
    notes: str = ""
