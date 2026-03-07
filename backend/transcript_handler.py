"""
transcript_handler.py — Handles transcript logging, buffering, and forwarding
"""

import asyncio
from collections import deque

import httpx

from models import TranscriptChunk

# Conversation buffer — stores last 50 transcript chunks
_conversation_buffer: deque[TranscriptChunk] = deque(maxlen=50)

CONVERSATION_MANAGER_URL = "http://localhost:8000/transcript_stream"


async def handle_transcript(chunk: TranscriptChunk) -> None:
    """
    Process a finalized transcript chunk:
    1. Log to console
    2. Store in conversation buffer
    3. Fire-and-forget forward to conversation manager
    """
    # Log to console
    print(
        f"[{chunk.timestamp:.1f}s] {chunk.speaker.upper()}: "
        f"{chunk.text} (confidence: {chunk.confidence:.2f})"
    )

    # Store in buffer
    _conversation_buffer.append(chunk)

    # Fire-and-forget forward to conversation manager
    asyncio.create_task(_forward_to_conversation_manager(chunk))


async def _forward_to_conversation_manager(chunk: TranscriptChunk) -> None:
    """POST transcript chunk to the conversation manager endpoint."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                CONVERSATION_MANAGER_URL,
                json=chunk.model_dump(),
                timeout=5.0,
            )
    except Exception as e:
        print(f"[transcript_handler] Failed to forward chunk: {e}")


def get_recent_transcripts(n: int = 50) -> list[TranscriptChunk]:
    """Return the last N transcript chunks from the buffer."""
    items = list(_conversation_buffer)
    return items[-n:]
