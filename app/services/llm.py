"""OpenRouter client calling Gemini models via the OpenAI-compatible API."""
from __future__ import annotations

import json
import re

import openai
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

SYSTEM_PROMPT = """You are an expert resume parser with 10+ years of HR and recruiting experience.
Your task is to extract structured information from resume text with maximum accuracy.

RULES:
1. Return ONLY valid JSON. No markdown, no explanation, no preamble, no backticks.
2. Extract information EXACTLY as written — do not infer or fabricate.
3. If a field is not present, use null (not empty string, not "N/A").
4. For dates: normalize ALL date formats to "YYYY-MM" format.
   Examples: "Jan 2021" -> "2021-01", "2021" -> "2021-01", "Present" -> null
5. For skills: extract every technical skill, tool, framework, language, platform mentioned.
   Include skills found in job descriptions, not just a "skills" section.
6. For experience: preserve full description text in the description field.
7. Phone numbers: include country code if present, preserve as string.
8. If the same company appears multiple times with different roles, create separate entries.
9. Education: extract GPA only if explicitly stated, never infer.
10. Do not skip ANY work experience entry, no matter how old."""


USER_PROMPT_TEMPLATE = """Parse the following resume and return a JSON object matching this exact schema.
Every field must be present in the output (use null if not found).

SCHEMA:
{{
  "personal_info": {{
    "full_name": "string | null",
    "email": "string | null",
    "phone": "string | null",
    "location": {{
      "city": "string | null",
      "state": "string | null",
      "country": "string | null",
      "full_address": "string | null"
    }},
    "linkedin_url": "string | null",
    "github_url": "string | null",
    "portfolio_url": "string | null",
    "other_urls": ["string"]
  }},
  "professional_summary": "string | null",
  "skills": {{
    "technical": ["string"],
    "soft": ["string"],
    "languages": ["string"],
    "tools": ["string"],
    "certifications_mentioned_as_skills": ["string"]
  }},
  "experience": [
    {{
      "company_name": "string | null",
      "job_title": "string | null",
      "employment_type": "full-time | part-time | contract | internship | freelance | null",
      "location": "string | null",
      "start_date": "YYYY-MM | null",
      "end_date": "YYYY-MM | null",
      "is_current": "boolean",
      "description": "string | null",
      "achievements": ["string"],
      "skills_mentioned": ["string"]
    }}
  ],
  "education": [
    {{
      "institution_name": "string | null",
      "degree_type": "Bachelor | Master | PhD | Associate | Diploma | Certificate | High School | null",
      "field_of_study": "string | null",
      "start_date": "YYYY-MM | null",
      "graduation_date": "YYYY-MM | null",
      "is_ongoing": "boolean",
      "gpa": "number | null",
      "gpa_scale": "number | null",
      "honors": "string | null",
      "activities": ["string"]
    }}
  ],
  "certifications": [
    {{
      "name": "string | null",
      "issuing_organization": "string | null",
      "issue_date": "YYYY-MM | null",
      "expiry_date": "YYYY-MM | null",
      "credential_id": "string | null",
      "credential_url": "string | null"
    }}
  ],
  "projects": [
    {{
      "name": "string | null",
      "description": "string | null",
      "technologies": ["string"],
      "url": "string | null",
      "start_date": "YYYY-MM | null",
      "end_date": "YYYY-MM | null"
    }}
  ],
  "languages_spoken": [
    {{
      "language": "string",
      "proficiency": "Native | Fluent | Professional | Conversational | Basic | null"
    }}
  ],
  "awards": [
    {{
      "title": "string | null",
      "issuer": "string | null",
      "date": "YYYY-MM | null",
      "description": "string | null"
    }}
  ],
  "publications": [
    {{
      "title": "string | null",
      "publisher": "string | null",
      "date": "YYYY-MM | null",
      "url": "string | null"
    }}
  ],
  "volunteer_experience": [
    {{
      "organization": "string | null",
      "role": "string | null",
      "start_date": "YYYY-MM | null",
      "end_date": "YYYY-MM | null",
      "description": "string | null"
    }}
  ],
  "parser_metadata": {{
    "total_years_experience": "number | null",
    "career_level": "Entry | Junior | Mid | Senior | Lead | Manager | Director | Executive | null",
    "primary_domain": "string | null",
    "resume_language": "string"
  }}
}}

RESUME TEXT:
---
{resume_text}
---"""


REPROMPT_TEMPLATE = """Your previous response was not valid JSON or was missing required fields.
Here is the error: {error_message}

Return ONLY the corrected JSON object. No explanation.
Original resume text is the same as before."""


_client: openai.AsyncOpenAI | None = None


def _get_client() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            default_headers={
                # OpenRouter uses these for its leaderboards; both are optional.
                "HTTP-Referer": "https://github.com/ats-parser",
                "X-Title": "ATS Resume Parser",
            },
        )
    return _client


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _CODE_FENCE_RE.sub("", stripped).strip()
    return stripped


@retry(
    retry=retry_if_exception_type(
        (
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
        )
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _raw_call(messages: list[dict]) -> str:
    client = _get_client()
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        # OpenRouter supports response_format for Gemini models that understand it;
        # harmless if the model ignores it.
        response_format={"type": "json_object"},
    )
    if not response.choices:
        return ""
    msg = response.choices[0].message
    return (msg.content or "").strip()


async def parse_resume_text(resume_text: str, max_reprompts: int = 3) -> tuple[dict, int]:
    """
    Call a Gemini model via OpenRouter to parse resume text into structured JSON.

    Retries with re-prompts up to max_reprompts if JSON parsing fails.
    Returns (parsed_dict, attempt_count).
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(resume_text=resume_text)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    last_error: str | None = None
    raw_response: str | None = None

    for attempt in range(1, max_reprompts + 1):
        if attempt > 1 and last_error is not None:
            # Multi-turn re-prompt: give the model its bad output + the error
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": raw_response or ""},
                {"role": "user", "content": REPROMPT_TEMPLATE.format(error_message=last_error)},
            ]

        logger.info(f"llm_call_started attempt={attempt} model={settings.LLM_MODEL}")
        try:
            raw_response = await _raw_call(messages)
        except openai.APIStatusError as e:
            logger.error(f"llm_api_error attempt={attempt} status={e.status_code} body={e.message}")
            last_error = f"OpenRouter API error {e.status_code}: {e.message}"
            continue
        except openai.OpenAIError as e:
            logger.error(f"llm_openai_error attempt={attempt} error={e}")
            last_error = f"OpenAI SDK error: {e}"
            continue
        except Exception as e:
            logger.error(f"llm_unknown_error attempt={attempt} error={e}")
            last_error = f"Unknown error: {e}"
            continue

        cleaned = _strip_code_fences(raw_response)
        try:
            parsed = json.loads(cleaned)
            logger.info(f"llm_parse_success attempt={attempt} tokens={len(cleaned)}")
            return parsed, attempt
        except json.JSONDecodeError as e:
            head = cleaned[:400].replace("\n", " ")
            tail = cleaned[-400:].replace("\n", " ") if len(cleaned) > 400 else ""
            logger.warning(
                f"llm_json_invalid attempt={attempt} error={e} "
                f"response_length={len(cleaned)} "
                f"HEAD={head!r} TAIL={tail!r}"
            )
            last_error = (
                f"JSON decode error: {e.msg} at line {e.lineno}, col {e.colno}. "
                f"Response was {len(cleaned)} chars."
            )
            continue

    raise ValueError(f"LLM parse failed after {max_reprompts} attempts. Last error: {last_error}")
