"""
main.py — FastAPI application entrypoint
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from audio_router import router as audio_router
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


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/transcripts")
async def get_transcripts(n: int = 50):
    """Return recent transcript chunks from the conversation buffer."""
    chunks = transcript_handler.get_recent_transcripts(n)
    return {"transcripts": [chunk.model_dump() for chunk in chunks]}


@app.post("/transcript_stream")
async def transcript_stream(chunk: TranscriptChunk):
    """
    Receive a transcript chunk from the transcript handler.
    This endpoint will later be replaced by the conversation manager.
    """
    # Append to the conversation buffer via the handler's buffer
    transcript_handler._conversation_buffer.append(chunk)
    return {"status": "ok"}
