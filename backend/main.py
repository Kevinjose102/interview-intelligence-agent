"""
main.py — FastAPI application entrypoint
"""

import asyncio
import json
import os
import tempfile
import shutil
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from audio_router import router as audio_router
from conversation_manager import manager as conversation_manager
from models import AnalysisInput, TranscriptChunk
import llm_reasoning_engine
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
# Summary endpoint (Groq-powered)
# ------------------------------------------------------------------ #

async def _generate_groq_summary(transcript_text: str) -> Optional[str]:
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

    # Load resume profile for consistency checking
    resume_data = None
    resume_path = os.path.join(os.path.dirname(__file__), "sample_resume.pdf")
    if os.path.exists(resume_path):
        try:
            from resume_intelligence.pipeline import process_resume
            profile = await asyncio.to_thread(process_resume, resume_path)
            resume_data = profile.model_dump()
            print(f"[analyze_latest] Resume loaded: {len(profile.skills)} skills, {len(profile.projects)} projects")
        except Exception as e:
            print(f"[analyze_latest] Resume load error: {e}")

    input_data = AnalysisInput(
        transcript_chunk=target_msg.text,
        speaker=target_msg.speaker,
        conversation_history=history,
        resume_profile=resume_data,
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
        from resume_intelligence.pipeline import process_resume
        from resume_intelligence.resume_analyzer import analyze_resume
        from resume_intelligence.resume_parser import extract_links
        from resume_intelligence.github_verifier import extract_github_username
        profile, raw_text = await asyncio.to_thread(process_resume, tmp_path)
        profile_dict = profile.model_dump() if hasattr(profile, "model_dump") else profile.dict()

        # Extract GitHub URL from resume
        links = extract_links(tmp_path)
        github_username = extract_github_username(links)
        profile_dict["github_username"] = github_username
        profile_dict["github_links"] = [l for l in links if "github.com" in l]

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


# ------------------------------------------------------------------ #
# Post-Interview Analysis
# ------------------------------------------------------------------ #

@app.post("/post_interview_analysis")
async def post_interview_analysis(payload: dict = {}):
    """
    Generate a comprehensive post-interview analysis report.
    Uses the full conversation transcript and optionally the uploaded resume profile.
    """
    resume_profile = payload.get("resume_profile", None)

    # Get the latest conversation
    conversations = conversation_manager.list_conversations()
    if not conversations:
        return {"error": "No conversations found"}

    latest = conversations[-1]
    conv = conversation_manager.get_conversation(latest.session_id)
    if conv is None or not conv.messages:
        return {"error": "Conversation has no messages"}

    # Build full transcript
    transcript_lines = []
    for msg in conv.messages:
        transcript_lines.append(f"{msg.speaker.upper()}: {msg.text}")
    transcript_text = "\n".join(transcript_lines)

    # Format resume
    resume_text = "Not provided"
    if resume_profile:
        resume_text = json.dumps(resume_profile, indent=2) if isinstance(resume_profile, dict) else str(resume_profile)

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your-groq-api-key-here":
        return {"error": "GROQ_API_KEY not configured"}

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        prompt = f"""You are a senior hiring manager and interview analyst. Generate a comprehensive POST-INTERVIEW ANALYSIS REPORT based on the complete interview transcript and candidate resume.

CANDIDATE RESUME PROFILE:
{resume_text}

FULL INTERVIEW TRANSCRIPT:
{transcript_text}

---

Generate a thorough analysis and return ONLY a JSON object with this EXACT structure:
{{
  "overall_score": <0-100 integer>,
  "verdict": "<one-line verdict e.g. 'Strong Technical Candidate with Leadership Potential'>",
  "summary": "<3-5 sentence interview summary covering key discussion points and candidate performance>",
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "skill_assessments": [
    {{"skill": "skill name", "score": <0-100>, "evidence": "brief evidence from interview"}}
  ],
  "consistency_notes": [
    {{"claim": "what resume says", "interview_evidence": "what candidate said", "status": "verified|inconsistent|unverified"}}
  ],
  "hiring_recommendation": "Strong Hire|Hire|Lean Hire|Lean No Hire|No Hire|Strong No Hire",
  "recommendation_reasoning": "<2-3 sentences explaining the hiring recommendation>",
  "suggested_next_steps": ["next step 1", "next step 2"]
}}

Rules:
- Be specific — cite actual statements from the transcript as evidence
- skill_assessments should cover 4-8 key skills discussed
- consistency_notes should compare resume claims vs actual interview answers
- overall_score: 85+ = exceptional, 70-84 = strong, 55-69 = moderate, below 55 = weak
- Be honest and fair in the assessment

Return ONLY valid JSON, no markdown, no explanation."""

        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a senior hiring manager producing a post-interview analysis report. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
        )

        import re
        raw = response.choices[0].message.content.strip()
        print(f"[post_interview] Raw response: {raw[:200]}...")

        # Parse JSON (handle markdown code blocks)
        json_text = raw
        if "```" in json_text:
            match = re.search(r"```(?:json)?\s*(.*?)```", json_text, re.DOTALL)
            if match:
                json_text = match.group(1).strip()

        report = json.loads(json_text)

        return {
            "status": "ok",
            "session_id": conv.session_id,
            "message_count": len(conv.messages),
            "duration": conv.duration,
            "report": report,
        }
    except json.JSONDecodeError as e:
        print(f"[post_interview] JSON parse error: {e}")
        return {"error": f"Failed to parse AI response: {e}"}
    except Exception as e:
        print(f"[post_interview] Error: {e}")
        return {"error": str(e)}


# ------------------------------------------------------------------ #
# GitHub Project Verification
# ------------------------------------------------------------------ #

@app.post("/verify/github")
async def verify_github(payload: dict):
    """
    Verify candidate projects by checking their GitHub repos and commit history.
    Accepts: {profile, transcript, github_username}
    Returns per-project verification with legitimacy scores.
    """
    profile = payload.get("profile", {})
    transcript = payload.get("transcript", "")
    github_username = payload.get("github_username") or profile.get("github_username")

    if not github_username:
        return {"error": "No GitHub username found. Upload a resume with a GitHub link first.", "projects": []}

    projects = profile.get("projects", [])
    if not projects:
        return {"error": "No projects found in resume profile", "projects": []}

    try:
        from resume_intelligence.github_verifier import verify_projects
        result = await verify_projects(projects, github_username, transcript)
        return {"status": "ok", **result}
    except Exception as e:
        print(f"[verify/github] Error: {e}")
        return {"error": str(e), "projects": []}
