"""
AI summarization — supports Claude (Anthropic), ChatGPT (OpenAI), and Gemini.

Provider is controlled by AI_PROVIDER in .env:
  AI_PROVIDER=claude   → uses ANTHROPIC_API_KEY + CLAUDE_MODEL
  AI_PROVIDER=openai   → uses OPENAI_API_KEY + OPENAI_MODEL
  AI_PROVIDER=gemini   → uses GEMINI_API_KEY + GEMINI_MODEL

Returns structured extraction (7 fields):
  {
    "summary": str,
    "tech_skills": [str],
    "soft_skills": [str],
    "remote_type": str | None,
    "city": str | None,
    "state": str | None,
    "region": str | None,
  }
"""
from __future__ import annotations

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a job-description analyst. "
    "Always respond with valid JSON only — no markdown, no explanation."
)

_USER_TEMPLATE = """Analyze the job posting below and return a JSON object with exactly seven fields:

"summary"     - 2-3 sentences: role overview, main responsibilities, company context.
"tech_skills" - array of ALL technical requirements (languages, frameworks, databases,
                tools, cloud platforms, CI/CD, etc.) found ANYWHERE in the posting.
"soft_skills" - array of ALL soft skills and work-style requirements found ANYWHERE
                in the posting.
"remote_type" - work arrangement: exactly one of "Remote", "Hybrid", "On-site".
                Read the full posting carefully — it may say "from home", "3 days office",
                "fully remote", or imply it from context.
                Use null only if truly impossible to determine.
"city"        - the primary work city in English, fully normalized:
                "TLV" → "Tel Aviv", "TA" → "Tel Aviv", "תל אביב" → "Tel Aviv",
                "באר שבע" → "Beer Sheva", "Be'er Sheva" → "Beer Sheva".
                Always use the canonical English full name.
                null if fully remote with no office.
"state"       - the COUNTRY the job is in, in English.
                For Israeli jobs this is always "Israel".
                Never put a district, region, or city here — only the country.
                null if truly unknown.
"region"      - the district OR broad area in English:
                "מחוז תל אביב" → "Tel Aviv District",
                "מרכז" → "Center", "North", "South", "Haifa District", "Sharon", etc.
                Use whatever is most specific and available from the posting.
                null if unknown.

Important: skills can appear in any section — extract ALL of them.
Use ALL provided fields (title, company, location, employment type, seniority) to
improve accuracy — especially for city, state, region, and remote_type.

Return ONLY valid JSON. Example:
{{
  "summary": "...",
  "tech_skills": ["Python", "Django", "PostgreSQL", "Redis", "Docker"],
  "soft_skills": ["Team player", "Self-learner", "Strong problem-solving skills"],
  "remote_type": "Hybrid",
  "city": "Tel Aviv",
  "state": "Israel",
  "region": "Tel Aviv District"
}}

Job posting:
Title:           {title}
Company:         {company}
Location (raw):  {location}
Employment type: {employment_type}
Seniority:       {seniority_level}
Description:
{description}"""


def _parse_result(raw: str) -> dict:
    """Strip markdown fences and parse JSON — shared by all providers."""
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    result = json.loads(text)
    remote_type = result.get("remote_type")
    city = result.get("city")
    state = result.get("state")
    region = result.get("region")
    return {
        "summary": str(result.get("summary", "")),
        "tech_skills": [s.strip() for s in result.get("tech_skills", []) if s],
        "soft_skills": [s.strip() for s in result.get("soft_skills", []) if s],
        "remote_type": str(remote_type).strip() if remote_type else None,
        "city": str(city).strip() if city else None,
        "state": str(state).strip() if state else None,
        "region": str(region).strip() if region else None,
    }


def _build_prompt(**kwargs) -> str:
    """Build the user prompt with all available job fields."""
    return _USER_TEMPLATE.format(
        title=kwargs.get("title") or "N/A",
        company=kwargs.get("company") or "N/A",
        location=kwargs.get("location") or "N/A",
        employment_type=kwargs.get("employment_type") or "N/A",
        seniority_level=kwargs.get("seniority_level") or "N/A",
        description=kwargs.get("description") or "",
    )


def _summarize_claude(**kwargs) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=800,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _build_prompt(**kwargs)}],
    )
    return _parse_result(message.content[0].text)


def _summarize_openai(**kwargs) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=800,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _build_prompt(**kwargs)},
        ],
    )
    return _parse_result(response.choices[0].message.content)


def _summarize_gemini(**kwargs) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction=_SYSTEM,
    )
    response = model.generate_content(_build_prompt(**kwargs))
    return _parse_result(response.text)


def summarize(
    description: str = "",
    title: str = "",
    company: str = "",
    location: str = "",
    employment_type: str = "",
    seniority_level: str = "",
) -> dict:
    """
    Route to the correct AI provider based on settings.AI_PROVIDER.
    Accepts full job context for better location/skill extraction.
    Supported values: "claude" | "openai" | "gemini"
    Falls back gracefully — callers never crash on AI errors.
    """
    provider = getattr(settings, "AI_PROVIDER", "claude").lower()
    kwargs = dict(
        description=description,
        title=title,
        company=company,
        location=location,
        employment_type=employment_type,
        seniority_level=seniority_level,
    )
    try:
        if provider == "openai":
            return _summarize_openai(**kwargs)
        if provider == "gemini":
            return _summarize_gemini(**kwargs)
        return _summarize_claude(**kwargs)
    except json.JSONDecodeError as exc:
        logger.warning("AI returned non-JSON (%s), using plain text fallback.", exc)
        return {"summary": str(exc), "tech_skills": [], "soft_skills": [],
                "remote_type": None, "city": None, "state": None, "region": None}
    except Exception as exc:
        logger.error("Summarization failed (provider=%s): %s", provider, exc)
        return {"summary": "", "tech_skills": [], "soft_skills": [],
                "remote_type": None, "city": None, "state": None, "region": None}
