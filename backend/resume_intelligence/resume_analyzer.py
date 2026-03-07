"""
resume_analyzer.py — Deep resume analysis using Groq (Llama 3.3 70B)

Analyses:
  1. Career trajectory anomaly detection
  2. Resume inflation classification
  3. Skill decay detection
  4. ATS compatibility scoring
  5. Overall resume quality score
"""

import asyncio
import json
import os
import re

from pydantic import BaseModel, Field


# ── Pydantic output models ──────────────────────────────────────────

class TrajectoryAnomaly(BaseModel):
    anomaly_type: str = ""          # "demotion", "gap", "short_tenure", "career_pivot"
    description: str = ""
    severity: str = "medium"        # "low", "medium", "high"
    time_period: str = ""

class InflationFlag(BaseModel):
    claim: str = ""
    reason: str = ""
    severity: str = "medium"        # "low", "medium", "high"
    category: str = ""              # "buzzword_stuffing", "vague_quantification", "scope_inflation", "title_inflation"

class DecayedSkill(BaseModel):
    skill: str = ""
    last_used: str = ""             # e.g. "2019", "3+ years ago"
    decay_risk: str = "medium"      # "low", "medium", "high"
    recommendation: str = ""

class ATSBreakdown(BaseModel):
    score: int = 0
    section_completeness: int = 0
    keyword_density: int = 0
    formatting_score: int = 0
    quantified_achievements: int = 0
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

class ResumeAnalysis(BaseModel):
    overall_score: int = 0                                      # 0-100
    overall_verdict: str = ""                                    # "Strong", "Average", "Weak"
    trajectory_anomalies: list[TrajectoryAnomaly] = Field(default_factory=list)
    trajectory_summary: str = ""
    inflation_flags: list[InflationFlag] = Field(default_factory=list)
    inflation_risk_level: str = "low"                           # "low", "medium", "high"
    inflation_summary: str = ""
    decayed_skills: list[DecayedSkill] = Field(default_factory=list)
    decay_summary: str = ""
    ats: ATSBreakdown = Field(default_factory=ATSBreakdown)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


# ── Prompt ──────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """You are an expert HR analyst and resume reviewer. Perform a deep analysis of this resume.

RESUME TEXT (raw extracted text):
{resume_text}

PARSED PROFILE (structured):
{profile_json}

---

Perform ALL of the following analyses and return a single JSON object:

1. **Career Trajectory Anomaly Detection**
   - Check for: demotions (senior→junior role jumps), unexplained gaps (>6 months), suspiciously short tenures (<6 months), drastic career pivots without explanation
   - For each anomaly, provide: anomaly_type, description, severity (low/medium/high), time_period

2. **Resume Inflation Classification**
   - Check for: buzzword stuffing (excessive jargon without substance), vague quantifications ("many projects", "various clients"), unrealistic scope claims (junior claiming to "lead 50-person teams"), title inflation
   - For each flag: claim, reason, severity (low/medium/high), category (buzzword_stuffing/vague_quantification/scope_inflation/title_inflation)
   - Set inflation_risk_level: low/medium/high

3. **Skill Decay Detection**
   - Identify skills only mentioned in older roles/projects (>3 years ago) with no evidence of recent usage
   - For each: skill, last_used (year or estimate), decay_risk (low/medium/high), recommendation

4. **ATS Compatibility Score**
   - Rate 0-100 overall ATS score
   - Sub-scores (0-100 each): section_completeness, keyword_density, formatting_score, quantified_achievements
   - List specific issues and actionable suggestions

5. **Overall Resume Quality**
   - overall_score: 0-100 weighted aggregate
   - overall_verdict: "Strong" (75+), "Average" (50-74), or "Weak" (<50)
   - strengths: top 3-5 resume strengths
   - weaknesses: top 3-5 areas for improvement

Return ONLY valid JSON matching this exact structure:
{{
  "overall_score": <0-100>,
  "overall_verdict": "<Strong|Average|Weak>",
  "trajectory_anomalies": [
    {{"anomaly_type": "<demotion|gap|short_tenure|career_pivot>", "description": "", "severity": "<low|medium|high>", "time_period": ""}}
  ],
  "trajectory_summary": "<1-2 sentence summary>",
  "inflation_flags": [
    {{"claim": "", "reason": "", "severity": "<low|medium|high>", "category": "<buzzword_stuffing|vague_quantification|scope_inflation|title_inflation>"}}
  ],
  "inflation_risk_level": "<low|medium|high>",
  "inflation_summary": "<1-2 sentence summary>",
  "decayed_skills": [
    {{"skill": "", "last_used": "", "decay_risk": "<low|medium|high>", "recommendation": ""}}
  ],
  "decay_summary": "<1-2 sentence summary>",
  "ats": {{
    "score": <0-100>,
    "section_completeness": <0-100>,
    "keyword_density": <0-100>,
    "formatting_score": <0-100>,
    "quantified_achievements": <0-100>,
    "issues": ["issue1", "issue2"],
    "suggestions": ["suggestion1", "suggestion2"]
  }},
  "strengths": ["strength1", "strength2"],
  "weaknesses": ["weakness1", "weakness2"]
}}

Return ONLY the JSON. No markdown, no explanation."""


async def analyze_resume(resume_text: str, profile_dict: dict) -> ResumeAnalysis:
    """
    Run all deep analyses on a resume using Groq (Llama 3.3 70B).
    Returns a structured ResumeAnalysis result.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your-groq-api-key-here":
        print("[resume_analyzer] No Groq API key — returning empty analysis")
        return ResumeAnalysis(
            overall_score=0,
            overall_verdict="Unavailable",
            trajectory_summary="Analysis unavailable — GROQ_API_KEY not set.",
            inflation_summary="Analysis unavailable.",
            decay_summary="Analysis unavailable.",
        )

    profile_json = json.dumps(profile_dict, indent=2) if profile_dict else "Not available"

    prompt = ANALYSIS_PROMPT.format(
        resume_text=resume_text[:6000],  # cap to avoid token limits
        profile_json=profile_json,
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
                        "content": (
                            "You are an expert HR analyst. "
                            "Analyze resumes and return structured JSON only. "
                            "Be critical but fair."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=3000,
            )
        )

        raw = response.choices[0].message.content.strip()
        print(f"[resume_analyzer] Raw LLM response length: {len(raw)}")

        # Extract JSON from response (handle markdown code blocks)
        json_text = raw
        if "```" in json_text:
            match = re.search(r"```(?:json)?\s*(.*?)```", json_text, re.DOTALL)
            if match:
                json_text = match.group(1).strip()

        parsed = json.loads(json_text)
        result = ResumeAnalysis(**parsed)

        print(
            f"[resume_analyzer] Analysis complete: "
            f"overall={result.overall_score}, "
            f"anomalies={len(result.trajectory_anomalies)}, "
            f"inflation_flags={len(result.inflation_flags)}, "
            f"decayed_skills={len(result.decayed_skills)}, "
            f"ats={result.ats.score}"
        )
        return result

    except json.JSONDecodeError as e:
        print(f"[resume_analyzer] JSON parse error: {e}")
        return ResumeAnalysis(
            overall_score=0,
            overall_verdict="Error",
            trajectory_summary="Analysis failed — could not parse LLM response.",
        )
    except Exception as e:
        print(f"[resume_analyzer] Error: {e}")
        return ResumeAnalysis(
            overall_score=0,
            overall_verdict="Error",
            trajectory_summary=f"Analysis failed: {str(e)}",
        )
