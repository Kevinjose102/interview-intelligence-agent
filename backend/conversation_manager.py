"""
conversation_manager.py — Interview conversation state manager

Sits between STT and the LLM Reasoning Engine:
- Stores conversation history per session
- Tracks speaker turns with same-speaker merging
- Provides context window for AI engine
- Broadcasts new messages via SSE for dashboard
"""

import asyncio
import json
import time
from collections import OrderedDict

from models import (
    Conversation,
    ConversationContext,
    ConversationMessage,
    ConversationSummary,
    TranscriptChunk,
)


class ConversationManager:
    """Singleton managing all active and completed interview conversations."""

    def __init__(self):
        # session_id → Conversation
        self._conversations: OrderedDict[str, Conversation] = OrderedDict()
        # SSE subscribers — each is an asyncio.Queue
        self._subscribers: list[asyncio.Queue] = []
        # Merge threshold: consecutive chunks from same speaker within this
        # window (seconds) get merged into one ConversationMessage
        self.merge_window_seconds = 5.0

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self, session_id: str) -> None:
        """Create a new conversation for this session (idempotent)."""
        if session_id in self._conversations:
            return
        self._conversations[session_id] = Conversation(
            session_id=session_id,
            start_time=time.time(),
        )
        print(f"[conversation_manager] Session started: {session_id}")

    def end_session(self, session_id: str) -> None:
        """Mark session as ended and compute duration."""
        conv = self._conversations.get(session_id)
        if conv is None:
            return
        conv.status = "ended"
        conv.end_time = time.time()
        conv.duration = round(conv.end_time - conv.start_time, 2)
        print(
            f"[conversation_manager] Session ended: {session_id} "
            f"({conv.duration}s, {len(conv.messages)} messages)"
        )

    # ------------------------------------------------------------------
    # Transcript ingestion
    # ------------------------------------------------------------------

    async def add_chunk(self, chunk: TranscriptChunk) -> None:
        """
        Process a finalized transcript chunk:
        1. Auto-create session if needed
        2. Merge with previous message if same speaker within window
        3. Broadcast to SSE subscribers
        """
        session_id = chunk.session_id

        # Auto-create session if it doesn't exist yet
        if session_id not in self._conversations:
            self.start_session(session_id)

        conv = self._conversations[session_id]
        now = time.time()

        # Try to merge with the last message if same speaker
        if (
            conv.messages
            and conv.messages[-1].speaker == chunk.speaker
            and (now - conv.messages[-1].end_time) < self.merge_window_seconds
        ):
            # Merge: append text, update end_time and confidence
            last_msg = conv.messages[-1]
            last_msg.text = f"{last_msg.text} {chunk.text}"
            last_msg.end_time = chunk.timestamp
            last_msg.confidence = (last_msg.confidence + chunk.confidence) / 2
        else:
            # New speaker turn
            msg = ConversationMessage(
                speaker=chunk.speaker,
                text=chunk.text,
                start_time=chunk.timestamp,
                end_time=chunk.timestamp,
                confidence=chunk.confidence,
            )
            conv.messages.append(msg)

        # Broadcast to SSE subscribers
        event = {
            "type": "new_message",
            "session_id": session_id,
            "speaker": chunk.speaker,
            "text": chunk.text,
            "timestamp": chunk.timestamp,
            "message_count": len(conv.messages),
        }
        await self._broadcast(event)

    # ------------------------------------------------------------------
    # Context for AI engine
    # ------------------------------------------------------------------

    def get_context(self, session_id: str, n: int = 10) -> ConversationContext | None:
        """
        Return the last N speaker turns for the AI reasoning engine.
        Includes both full ConversationMessage objects and a simplified
        conversation_history list for direct LLM prompting.
        """
        conv = self._conversations.get(session_id)
        if conv is None:
            return None

        recent = conv.messages[-n:]
        history = [{"speaker": m.speaker, "text": m.text} for m in recent]

        return ConversationContext(
            session_id=session_id,
            recent_messages=recent,
            conversation_history=history,
        )

    # ------------------------------------------------------------------
    # Query APIs
    # ------------------------------------------------------------------

    def get_conversation(self, session_id: str) -> Conversation | None:
        return self._conversations.get(session_id)

    def list_conversations(self) -> list[ConversationSummary]:
        return [c.to_summary() for c in self._conversations.values()]

    def get_active_sessions(self) -> list[str]:
        return [
            sid
            for sid, c in self._conversations.items()
            if c.status == "active"
        ]

    # ------------------------------------------------------------------
    # SSE broadcasting
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        """Create a new SSE subscriber queue."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove an SSE subscriber."""
        self._subscribers = [s for s in self._subscribers if s is not q]

    async def _broadcast(self, event: dict) -> None:
        """Push event to all SSE subscribers."""
        dead: list[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        # Remove dead subscribers
        for q in dead:
            self.unsubscribe(q)


# Module-level singleton
manager = ConversationManager()
