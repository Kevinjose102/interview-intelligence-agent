"""
main.py — FastAPI application entrypoint
"""

import asyncio
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from audio_router import router as audio_router
from conversation_manager import manager as conversation_manager
from models import TranscriptChunk
import transcript_handler

# Load environment variables from .env
load_dotenv()

app = FastAPI(
    title="Interview Intelligence Agent",
    description="Real-time Google Meet audio transcription via Deepgram",
    version="1.0.0",
)

# CORS middleware — allow all origins (prototype only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include WebSocket audio router
app.include_router(audio_router)


# ------------------------------------------------------------------ #
# Health & legacy endpoints
# ------------------------------------------------------------------ #

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/transcripts")
async def get_transcripts(n: int = 50):
    """Return recent raw transcript chunks (backward compatible)."""
    chunks = transcript_handler.get_recent_transcripts(n)
    return {"transcripts": [chunk.model_dump() for chunk in chunks]}


# ------------------------------------------------------------------ #
# Transcript stream (receives chunks — kept for API compatibility)
# ------------------------------------------------------------------ #

@app.post("/transcript_stream")
async def transcript_stream(chunk: TranscriptChunk):
    """
    Receive a transcript chunk and route it through the conversation manager.
    """
    await conversation_manager.add_chunk(chunk)
    return {"status": "ok"}


# ------------------------------------------------------------------ #
# Conversation endpoints
# ------------------------------------------------------------------ #

@app.get("/conversations")
async def list_conversations():
    """List all conversations (summaries)."""
    summaries = conversation_manager.list_conversations()
    return {"conversations": [s.model_dump() for s in summaries]}


@app.get("/conversations/active")
async def get_active_sessions():
    """Return list of active session IDs."""
    return {"active_sessions": conversation_manager.get_active_sessions()}


@app.get("/conversations/stream")
async def conversation_sse_stream():
    """
    Server-Sent Events stream — real-time new messages for the dashboard.
    Connect via EventSource in the browser.
    """
    queue = conversation_manager.subscribe()

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                data = json.dumps(event)
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            conversation_manager.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/conversations/{session_id}")
async def get_conversation(session_id: str):
    """Return full conversation with all messages."""
    conv = conversation_manager.get_conversation(session_id)
    if conv is None:
        return {"error": "Session not found"}, 404
    return conv.model_dump()


@app.get("/conversations/{session_id}/context")
async def get_conversation_context(
    session_id: str,
    n: int = Query(default=10, description="Number of recent turns"),
):
    """Return recent context window for AI engine."""
    ctx = conversation_manager.get_context(session_id, n=n)
    if ctx is None:
        return {"error": "Session not found"}, 404
    return ctx.model_dump()


@app.post("/conversations/{session_id}/end")
async def end_conversation(session_id: str):
    """Manually end an active session."""
    conv = conversation_manager.get_conversation(session_id)
    if conv is None:
        return {"error": "Session not found"}, 404
    conversation_manager.end_session(session_id)
    return {"status": "ended", "session_id": session_id}
