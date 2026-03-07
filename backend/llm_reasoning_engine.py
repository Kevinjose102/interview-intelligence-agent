"""
llm_reasoning_engine.py — AI analysis of candidate responses

Takes conversation context + resume profile → produces:
- Follow-up questions
- Resume consistency flags
- Answer quality score (0-100)
- Skill confidence updates

Uses Groq (Llama 3.3 70B) for fast inference.
"""

import asyncio
import json
import os
from typing import Dict, Optional

from models import AnalysisInput, AnalysisResult


ANALYSIS_PROMPT = """You are an expert interview analysis AI. Analyze the candidate's latest response in the context of the conversation and their resume.

RESUME PROFILE:
{resume_profile}

RESUME CONTEXT (relevant details):
{resume_context}

CONVERSATION SO FAR:
{conversation_history}

LATEST MESSAGE:
{speaker}: {transcript_chunk}

CONVERSATION SUMMARY:
{conversation_summary}

---

Analyze this and return a JSON object with EXACTLY this structure:
{{
  "follow_up_questions": ["question1", "question2"],
  "consistency_flags": ["flag1 if any mismatch between resume and answers"],
  "answer_quality_score": <0-100 integer>,
  "skill_confidence_updates": {{"skill_name": <0-100 confidence>}}
}}

Rules:
- follow_up_questions: Generate 2-3 deeper technical questions based on what the candidate said. These should help the interviewer probe further.
- consistency_flags: Flag ANY mismatch between resume claims and what the candidate said. If no mismatch, return empty list.
- answer_quality_score: Rate 0-100. Consider technical depth, clarity, and accuracy. 80+ = strong, 50-79 = moderate, below 50 = weak/vague.
- skill_confidence_updates: For each skill mentioned or demonstrated, rate confidence 0-100 based on how well the candidate explained it.

Return ONLY valid JSON, no markdown, no explanation."""


# Store latest analysis per session
_analysis_cache: Dict[str, AnalysisResult] = {}


async def analyze(input_data: AnalysisInput) -> AnalysisResult:
    """
    Run LLM analysis on the candidate's latest response.
    Returns structured AnalysisResult.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your-groq-api-key-here":
        print("[reasoning_engine] No Groq API key — returning empty analysis")
        return AnalysisResult()

    # Format conversation history
    history_text = "\n".join(
        f"{turn.get('speaker', 'unknown').upper()}: {turn.get('text', '')}"
        for turn in input_data.conversation_history
    )

    # Format resume profile
    resume_text = "Not provided"
    if input_data.resume_profile:
        resume_text = json.dumps(input_data.resume_profile, indent=2)

    # Build the prompt
    prompt = ANALYSIS_PROMPT.format(
        resume_profile=resume_text,
        resume_context=input_data.resume_context or "Not available",
        conversation_history=history_text or "No prior conversation",
        speaker=input_data.speaker.upper(),
        transcript_chunk=input_data.transcript_chunk,
        conversation_summary=input_data.conversation_summary or "No summary yet",
    )

    try:
        from groq import Groq

        client = Groq(api_key=api_key)

        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an interview analysis AI. Always respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
        )

        raw = response.choices[0].message.content.strip()
        print(f"[reasoning_engine] Raw LLM response: {raw[:200]}...")

        # Parse JSON from response (handle markdown code blocks)
        json_text = raw
        if "```" in json_text:
            import re
            match = re.search(r"```(?:json)?\s*(.*?)```", json_text, re.DOTALL)
            if match:
                json_text = match.group(1).strip()

        parsed = json.loads(json_text)
        result = AnalysisResult(**parsed)

        # Cache the result
        if input_data.session_id:
            _analysis_cache[input_data.session_id] = result

        print(
            f"[reasoning_engine] Analysis complete: "
            f"quality={result.answer_quality_score}, "
            f"follow_ups={len(result.follow_up_questions)}, "
            f"flags={len(result.consistency_flags)}"
        )
        return result

    except json.JSONDecodeError as e:
        print(f"[reasoning_engine] JSON parse error: {e}")
        return AnalysisResult()
    except Exception as e:
        print(f"[reasoning_engine] Error: {e}")
        return AnalysisResult()


def get_cached_analysis(session_id: str) -> Optional[AnalysisResult]:
    """Return the latest cached analysis for a session."""
    return _analysis_cache.get(session_id)


def get_all_analyses() -> Dict[str, AnalysisResult]:
    """Return all cached analyses."""
    return _analysis_cache.copy()
