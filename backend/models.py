"""
models.py — Pydantic models for transcript data
"""

from pydantic import BaseModel


class TranscriptChunk(BaseModel):
    speaker: str  # "candidate" or "interviewer"
    text: str
    timestamp: float
    confidence: float
    is_final: bool
    session_id: str


class SessionMetadata(BaseModel):
    session_id: str
    start_time: float
