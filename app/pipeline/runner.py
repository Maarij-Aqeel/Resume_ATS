"""End-to-end pipeline orchestration."""
from __future__ import annotations

import time
from dataclasses import dataclass

from loguru import logger

from app.models.schemas import ResumeSchema
from app.pipeline.extractor import ExtractedDocument, extract_document
from app.pipeline.normalizer import normalize_resume
from app.pipeline.parser import parse
from app.pipeline.validator import compute_confidence


@dataclass
class PipelineResult:
    schema: ResumeSchema
    extracted: ExtractedDocument
    confidence: float
    parse_attempts: int
    total_time_ms: int


async def run_pipeline(filename: str, content: bytes) -> PipelineResult:
    """Run extractor -> parser -> validator -> normalizer. Returns final result."""
    t0 = time.time()
    extracted = extract_document(filename, content)
    if not extracted.raw_text or len(extracted.raw_text) < 50:
        raise ValueError(f"Extraction produced unusable text (length={len(extracted.raw_text)})")

    schema, attempts, _ = await parse(extracted.raw_text)
    schema = normalize_resume(schema)
    confidence = compute_confidence(schema)

    total = int((time.time() - t0) * 1000)
    logger.info(
        "pipeline_complete",
        filename=filename,
        confidence=confidence,
        parse_attempts=attempts,
        total_time_ms=total,
    )
    return PipelineResult(
        schema=schema,
        extracted=extracted,
        confidence=confidence,
        parse_attempts=attempts,
        total_time_ms=total,
    )
