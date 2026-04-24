"""Layer 2: LLM parsing — turns raw resume text into a ResumeSchema."""
from __future__ import annotations

from loguru import logger

from app.models.schemas import ResumeSchema
from app.pipeline.validator import validate_parsed
from app.services import llm


async def parse(resume_text: str) -> tuple[ResumeSchema, int, dict]:
    """
    Parse raw resume text into a validated ResumeSchema.

    Returns (schema, attempt_count, raw_parsed_dict).
    Raises ValueError on unrecoverable failure.
    """
    if not resume_text or len(resume_text) < 50:
        raise ValueError("Resume text is empty or too short")

    parsed_dict, attempts = await llm.parse_resume_text(resume_text)
    schema = validate_parsed(parsed_dict)
    logger.info("parse_validated", attempts=attempts, experience_count=len(schema.experience))
    return schema, attempts, parsed_dict


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m app.pipeline.parser <text_file>")
        sys.exit(1)

    text = open(sys.argv[1], encoding="utf-8").read()
    schema, attempts, _ = asyncio.run(parse(text))
    print(f"attempts: {attempts}")
    print(schema.model_dump_json(indent=2))
