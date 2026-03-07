"""
transcript_handler.py — Handles transcript logging, buffering, and forwarding
"""

from collections import deque

from conversation_manager import manager as conversation_manager
from models import TranscriptChunk

# Raw transcript buffer — stores last 50 chunks (backward compatible)
_conversation_buffer: deque[TranscriptChunk] = deque(maxlen=50)


async def handle_transcript(chunk: TranscriptChunk) -> None:
    """
    Process a finalized transcript chunk:
    1. Log to console
    2. Store in raw buffer (backward compat with /transcripts)
    3. Forward to conversation manager (merges turns, broadcasts SSE)
    """
    # Log to console
    print(
        f"[{chunk.timestamp:.1f}s] {chunk.speaker.upper()}: "
        f"{chunk.text} (confidence: {chunk.confidence:.2f})"
    )

    # Store in raw buffer
    _conversation_buffer.append(chunk)

    # Forward to conversation manager
    await conversation_manager.add_chunk(chunk)


def get_recent_transcripts(n: int = 50) -> list[TranscriptChunk]:
    """Return the last N transcript chunks from the buffer."""
    items = list(_conversation_buffer)
    return items[-n:]
