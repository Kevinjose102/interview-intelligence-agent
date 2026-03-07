"""
models.py — Pydantic models for transcript and conversation data
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
    end_time: float | None = None
    status: str = "active"  # "active" or "ended"
    messages: list[ConversationMessage] = []
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


# ------------------------------------------------------------------ #
# LLM Reasoning Engine models
# ------------------------------------------------------------------ #

class AnalysisInput(BaseModel):
    """Input payload for the LLM Reasoning Engine."""
    transcript_chunk: str  # latest candidate answer
    speaker: str  # who said it
    conversation_history: list[dict]  # [{speaker, text}]
    resume_profile: dict | None = None  # structured resume (skills, projects, experience)
    resume_context: str | None = None  # retrieved resume context (RAG)
    conversation_summary: str | None = None  # summary so far
    session_id: str = ""


class AnalysisResult(BaseModel):
    """Output from the LLM Reasoning Engine."""
    follow_up_questions: list[str] = []
    consistency_flags: list[str] = []
    answer_quality_score: int = 0  # 0-100
    skill_confidence_updates: dict[str, int] = {}  # skill → confidence 0-100
