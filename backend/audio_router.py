"""
audio_router.py — WebSocket endpoint bridging Chrome Extension ↔ Deepgram
"""

import asyncio
import json
import os
import uuid

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import transcript_handler
from conversation_manager import manager as conversation_manager
from models import TranscriptChunk

router = APIRouter()

DEEPGRAM_WS_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2"
    "&punctuate=true"
    "&interim_results=true"
    "&utterance_end_ms=1000"
)


def get_deepgram_api_key() -> str:
    """Read API key at request time (after dotenv has loaded in main.py)."""
    key = os.getenv("DEEPGRAM_API_KEY", "")
    if not key:
        print("[audio_stream] WARNING: DEEPGRAM_API_KEY is not set!")
    return key


@router.websocket("/audio_stream/{speaker}")
async def audio_stream(websocket: WebSocket, speaker: str):
    """
    WebSocket endpoint for audio streaming.

    Accepts audio from the Chrome Extension, forwards it to Deepgram,
    and processes the returned transcripts.
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())
    print(f"[audio_stream] Connection opened: speaker={speaker}, session={session_id}")

    # Register session with conversation manager
    conversation_manager.start_session(session_id)

    # Track metadata for the current pending audio chunk
    pending_metadata = {"speaker": speaker, "timestamp": 0.0}

    deepgram_ws = None

    try:
        # Open a fresh Deepgram WebSocket connection for this session
        api_key = get_deepgram_api_key()
        additional_headers = {"Authorization": f"Token {api_key}"}
        deepgram_ws = await websockets.connect(
            DEEPGRAM_WS_URL,
            additional_headers=additional_headers,
            open_timeout=30,
            ping_interval=None,  # Disable default pings — Deepgram doesn't respond to them
        )
        print(f"[audio_stream] Deepgram connected for {speaker}")

        # Run three concurrent tasks (including Deepgram KeepAlive)
        await asyncio.gather(
            _receive_from_extension(websocket, deepgram_ws, pending_metadata),
            _receive_from_deepgram(
                deepgram_ws, websocket, speaker, session_id, pending_metadata
            ),
            _deepgram_keepalive(deepgram_ws),
        )

    except WebSocketDisconnect:
        print(f"[audio_stream] Extension disconnected: {speaker}")
    except websockets.exceptions.ConnectionClosed:
        print(f"[audio_stream] Deepgram connection closed: {speaker}")
    except Exception as e:
        print(f"[audio_stream] Error for {speaker}: {e}")
    finally:
        # Clean up Deepgram connection
        if deepgram_ws:
            try:
                await deepgram_ws.close()
            except Exception:
                pass
        # End session in conversation manager
        conversation_manager.end_session(session_id)
        print(f"[audio_stream] Connection closed: speaker={speaker}, session={session_id}")


async def _deepgram_keepalive(dg_ws) -> None:
    """Send Deepgram-specific KeepAlive messages every 8 seconds."""
    try:
        while True:
            await asyncio.sleep(8)
            await dg_ws.send(json.dumps({"type": "KeepAlive"}))
    except Exception:
        pass  # Connection closed — exit silently

async def _receive_from_extension(
    ext_ws: WebSocket,
    dg_ws: websockets.WebSocketClientProtocol,
    pending_metadata: dict,
):
    """
    Receive data from the Chrome Extension WebSocket.
    - Text frames → parse as JSON metadata
    - Binary frames → forward to Deepgram
    """
    chunk_count = 0
    try:
        while True:
            data = await ext_ws.receive()

            if "text" in data and data["text"]:
                # JSON metadata frame
                meta = json.loads(data["text"])
                pending_metadata["speaker"] = meta.get("speaker", pending_metadata["speaker"])
                pending_metadata["timestamp"] = meta.get("timestamp", 0.0)

            elif "bytes" in data and data["bytes"]:
                # Binary audio chunk → forward to Deepgram
                chunk_count += 1
                if chunk_count <= 3 or chunk_count % 20 == 0:
                    print(f"[receive_from_extension] Forwarding chunk #{chunk_count} ({len(data['bytes'])} bytes) for {pending_metadata['speaker']}")
                await dg_ws.send(data["bytes"])

    except WebSocketDisconnect:
        # Signal Deepgram that audio is done
        try:
            await dg_ws.send(json.dumps({"type": "CloseStream"}))
        except Exception:
            pass
        raise
    except Exception as e:
        print(f"[receive_from_extension] Error: {e}")
        raise


async def _receive_from_deepgram(
    dg_ws: websockets.WebSocketClientProtocol,
    ext_ws: WebSocket,
    speaker: str,
    session_id: str,
    pending_metadata: dict,
):
    """
    Receive transcript results from Deepgram and process them.
    Only final transcripts with non-empty text are forwarded.
    """
    try:
        async for message in dg_ws:
            try:
                result = json.loads(message)
            except json.JSONDecodeError:
                continue

            # Skip non-result messages (e.g. metadata, UtteranceEnd)
            if "channel" not in result:
                continue

            try:
                # Extract transcript data from Deepgram response
                channel = result["channel"]

                # channel must be a dict (Deepgram sometimes sends other types)
                if not isinstance(channel, dict):
                    continue

                alternatives = channel.get("alternatives", [])

                if not alternatives:
                    continue

                best = alternatives[0]
                transcript_text = best.get("transcript", "").strip()
                confidence = best.get("confidence", 0.0)
                is_final = result.get("is_final", False)

                # Only process non-empty final transcripts
                if transcript_text and is_final:
                    chunk = TranscriptChunk(
                        speaker=speaker,
                        text=transcript_text,
                        timestamp=pending_metadata.get("timestamp", 0.0),
                        confidence=confidence,
                        is_final=True,
                        session_id=session_id,
                    )

                    await transcript_handler.handle_transcript(chunk)
            except (KeyError, TypeError, IndexError, AttributeError) as parse_err:
                print(f"[receive_from_deepgram] Parse error: {parse_err}")
                continue

    except websockets.exceptions.ConnectionClosed:
        print(f"[receive_from_deepgram] Connection closed for {speaker}")
    except Exception as e:
        print(f"[receive_from_deepgram] Error: {e}")
