"""
main.py — FastAPI application entrypoint
"""

import asyncio
import json
import os
import tempfile
import shutil

from dotenv import load_dotenv
from fastapi import FastAPI, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from audio_router import router as audio_router
from conversation_manager import manager as conversation_manager
from models import AnalysisInput, TranscriptChunk
import llm_reasoning_engine
import transcript_handler
from resume_intelligence.pipeline import process_resume
from resume_intelligence.resume_analyzer import analyze_resume

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
# Summary endpoint (Groq-powered)
# ------------------------------------------------------------------ #

async def _generate_groq_summary(transcript_text: str) -> str | None:
    """Use Groq (Llama 3) to generate an intelligent interview summary."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your-groq-api-key-here":
        return None

    try:
        from groq import Groq

        client = Groq(api_key=api_key)

        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an interview analysis assistant. "
                            "Summarize the interview conversation in 3-5 sentences. "
                            "Focus on: topics discussed, key points by the candidate, "
                            "and notable observations."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Transcript:\n{transcript_text}",
                    },
                ],
                temperature=0.3,
                max_tokens=500,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[summary] Groq error: {e}")
        return None


@app.get("/summary")
async def get_summary():
    """
    Return a summary of the most recent conversation:
    - summary: AI-generated summary via Groq (falls back to raw transcript)
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

    # Generate AI summary via Groq (falls back to raw transcript)
    ai_summary = await _generate_groq_summary(raw_transcript)

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
        "summary_source": "groq" if ai_summary else "raw_transcript",
        "last_4_messages": last_4,
        "latest_message": latest,
    }


# ------------------------------------------------------------------ #
# LLM Reasoning Engine endpoints
# ------------------------------------------------------------------ #

@app.post("/ai_analysis")
async def run_analysis(input_data: AnalysisInput):
    """
    Run LLM reasoning engine analysis on a candidate response.
    Returns follow-up questions, consistency flags, quality score,
    and skill confidence updates.
    """
    result = await llm_reasoning_engine.analyze(input_data)
    return result.model_dump()


@app.get("/analysis_results/{session_id}")
async def get_analysis_results(session_id: str):
    """Return the latest cached analysis for a session."""
    result = llm_reasoning_engine.get_cached_analysis(session_id)
    if result is None:
        return {"error": "No analysis found for this session"}
    return result.model_dump()


@app.get("/analysis_results")
async def get_all_analysis_results():
    """Return all cached analysis results."""
    analyses = llm_reasoning_engine.get_all_analyses()
    return {
        sid: r.model_dump()
        for sid, r in analyses.items()
    }


@app.get("/analyze_latest")
async def analyze_latest():
    """
    One-click analysis: auto-pull the latest conversation and run
    the LLM reasoning engine on the most recent candidate answer.
    """
    # Get the latest conversation
    conversations = conversation_manager.list_conversations()
    if not conversations:
        return {"error": "No conversations found"}

    latest = conversations[-1]
    conv = conversation_manager.get_conversation(latest.session_id)
    if conv is None or not conv.messages:
        return {"error": "Conversation has no messages"}

    # Build conversation history
    history = [{"speaker": m.speaker, "text": m.text} for m in conv.messages]

    # Find the last candidate message for analysis
    last_candidate_msg = None
    for msg in reversed(conv.messages):
        if msg.speaker == "candidate":
            last_candidate_msg = msg
            break

    # If no candidate message, analyze the last message regardless
    target_msg = last_candidate_msg or conv.messages[-1]

    input_data = AnalysisInput(
        transcript_chunk=target_msg.text,
        speaker=target_msg.speaker,
        conversation_history=history,
        resume_profile=None,  # TODO: integrate with resume intelligence
        resume_context=None,
        conversation_summary=None,
        session_id=conv.session_id,
    )

    result = await llm_reasoning_engine.analyze(input_data)
    return {
        "session_id": conv.session_id,
        "analyzed_message": {
            "speaker": target_msg.speaker,
            "text": target_msg.text,
        },
        "analysis": result.model_dump(),
    }


# ------------------------------------------------------------------ #
# Resume upload & analysis
# ------------------------------------------------------------------ #

@app.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """
    Accept a PDF resume, run the resume intelligence pipeline,
    and return structured profile data (skills, projects, experience).
    """
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are supported"}

    # Save uploaded file to a temp location
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, file.filename)
    try:
        with open(tmp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Run pipeline (sync — runs in thread to avoid blocking)
        profile, raw_text = await asyncio.to_thread(process_resume, tmp_path)
        profile_dict = profile.model_dump() if hasattr(profile, "model_dump") else profile.dict()

        # Run deep analysis (async — uses Groq)
        deep_analysis = await analyze_resume(raw_text, profile_dict)

        return {
            "status": "ok",
            "profile": profile_dict,
            "deep_analysis": deep_analysis.model_dump(),
        }
    except Exception as e:
        print(f"[resume/upload] Error: {e}")
        return {"error": str(e)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ------------------------------------------------------------------ #
# Follow-up question generation
# ------------------------------------------------------------------ #

@app.post("/resume/questions")
async def generate_follow_up_questions(payload: dict):
    """
    Generate follow-up interview questions based on resume profile
    and (optionally) live transcript context.
    """
    profile = payload.get("profile", {})
    transcript_context = payload.get("transcript_context", "")

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your-groq-api-key-here":
        return {"error": "GROQ_API_KEY not configured", "questions": []}

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        profile_text = json.dumps(profile, indent=2) if isinstance(profile, dict) else str(profile)

        prompt = f"""You are a senior technical interviewer. Based on the candidate's resume and the interview transcript so far, generate 5 insightful follow-up questions that:
1. Probe deeper into claimed skills and projects
2. Test practical understanding (not just buzzwords)
3. Identify potential gaps or inconsistencies
4. Are specific, not generic

Resume Profile:
{profile_text}

Transcript so far:
{transcript_context if transcript_context else '(Interview has not started yet)'}

Return ONLY a JSON array of objects, each with "question" and "category" (one of: "technical_depth", "project_experience", "skill_verification", "behavioral", "gap_analysis") fields. No other text."""

        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a senior technical interviewer generating probing follow-up questions."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=1000,
            )
        )

        import re
        raw = response.choices[0].message.content
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            questions = json.loads(match.group(0))
        else:
            questions = [{"question": raw, "category": "general"}]

        return {"status": "ok", "questions": questions}
    except Exception as e:
        print(f"[resume/questions] Error: {e}")
        return {"error": str(e), "questions": []}


# ------------------------------------------------------------------ #
# Consistency analysis
# ------------------------------------------------------------------ #

@app.post("/analyze/consistency")
async def analyze_consistency(payload: dict):
    """
    Analyze consistency between what the candidate says in the interview
    and what their resume claims.
    """
    profile = payload.get("profile", {})
    transcript = payload.get("transcript", "")

    if not transcript:
        return {"error": "No transcript provided", "analysis": []}

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your-groq-api-key-here":
        return {"error": "GROQ_API_KEY not configured", "analysis": []}

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        profile_text = json.dumps(profile, indent=2) if isinstance(profile, dict) else str(profile)

        prompt = f"""You are an interview analysis AI. Compare the candidate's interview responses against their resume to identify:
1. Verified claims — statements that align with or confirm resume content
2. Inconsistencies — contradictions between spoken answers and resume
3. Depth indicators — does the candidate show genuine understanding or just surface knowledge?
4. Red flags — vague answers, topic avoidance, contradictory timelines

Resume Profile:
{profile_text}

Interview Transcript:
{transcript}

Return ONLY a JSON array of objects, each with:
- "claim": the specific claim or statement being analyzed
- "status": one of "verified", "inconsistent", "unverifiable", "red_flag"
- "confidence": 0-100 score
- "explanation": brief explanation
- "source": "resume" or "transcript"

No other text."""

        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are an interview consistency analysis engine."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=2000,
            )
        )

        import re
        raw = response.choices[0].message.content
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            analysis = json.loads(match.group(0))
        else:
            analysis = []

        # Compute overall score
        if analysis:
            verified = sum(1 for a in analysis if a.get("status") == "verified")
            total = len(analysis)
            overall_score = round((verified / total) * 100)
        else:
            overall_score = 0

        return {
            "status": "ok",
            "analysis": analysis,
            "overall_score": overall_score,
            "total_claims": len(analysis),
        }
    except Exception as e:
        print(f"[analyze/consistency] Error: {e}")
        return {"error": str(e), "analysis": []}

