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


# ------------------------------------------------------------------ #
# Summary endpoint (Gemini-powered)
# ------------------------------------------------------------------ #

async def _generate_gemini_summary(transcript_text: str) -> str | None:
    """Use Gemini to generate an intelligent interview summary."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key == "your-gemini-api-key-here":
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = (
            "You are an interview analysis assistant. "
            "Summarize the following interview conversation in 3-5 sentences. "
            "Focus on: what topics were discussed, key points made by the candidate, "
            "and any notable observations.\n\n"
            f"Transcript:\n{transcript_text}"
        )

        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        return response.text
    except Exception as e:
        print(f"[summary] Gemini error: {e}")
        return None


@app.get("/summary")
async def get_summary():
    """
    Return a summary of the most recent conversation:
    - summary: AI-generated summary via Gemini (falls back to raw transcript)
    - last_4_messages: the 4 most recent speaker turns
    - latest_message: the single latest speaker turn
    - stats: message count, duration, speakers
    """
    conversations = conversation_manager.list_conversations()
    if not conversations:
        return {
            "error": "No conversations found",
            "summary": None,
            "last_4_messages": [],
            "latest_message": None,
        }

    # Get the most recent conversation (last in the list)
    latest_summary = conversations[-1]
    conv = conversation_manager.get_conversation(latest_summary.session_id)
    if conv is None or not conv.messages:
        return {
            "error": "Conversation has no messages",
            "summary": None,
            "last_4_messages": [],
            "latest_message": None,
        }

    messages = conv.messages

    # Build raw transcript text
    transcript_lines = []
    for msg in messages:
        transcript_lines.append(f"{msg.speaker.upper()}: {msg.text}")
    raw_transcript = "\n".join(transcript_lines)

    # Generate AI summary via Gemini (falls back to raw transcript)
    ai_summary = await _generate_gemini_summary(raw_transcript)

    # Count per-speaker stats
    speaker_counts: dict[str, int] = {}
    for msg in messages:
        speaker_counts[msg.speaker] = speaker_counts.get(msg.speaker, 0) + 1

    # Last 4 messages
    last_4 = [m.model_dump() for m in messages[-4:]]

    # Latest message
    latest = messages[-1].model_dump()

    return {
        "session_id": conv.session_id,
        "status": conv.status,
        "stats": {
            "total_messages": len(messages),
            "duration_seconds": conv.duration,
            "speakers": speaker_counts,
        },
        "summary": ai_summary if ai_summary else raw_transcript,
        "summary_source": "gemini" if ai_summary else "raw_transcript",
        "last_4_messages": last_4,
        "latest_message": latest,
    }
