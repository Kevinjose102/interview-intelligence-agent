"""
models.py — Pydantic models for transcript and conversation data
"""

from pydantic import BaseModel
from typing import Optional
from pydantic import Field

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


class ConversationMessage(BaseModel):
    """A single speaker turn in the conversation."""
    speaker: str
    text: str
    start_time: float
    end_time: float
    confidence: float


class Conversation(BaseModel):
    """Full conversation for a session."""
    session_id: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "active"
    messages: list[ConversationMessage] = Field(default_factory=list)
    duration: float = 0.0

    def to_summary(self) -> "ConversationSummary":
        return ConversationSummary(
            session_id=self.session_id,
            start_time=self.start_time,
            status=self.status,
            message_count=len(self.messages),
            duration=self.duration,
        )


class ConversationSummary(BaseModel):
    """Lightweight conversation summary."""
    session_id: str
    start_time: float
    status: str
    message_count: int
    duration: float


class ConversationContext(BaseModel):
    """Sliding window of recent turns — payload for the AI engine."""
    session_id: str
    recent_messages: list[ConversationMessage]
    conversation_history: list[dict]  # simplified [{speaker, text}] for LLM
