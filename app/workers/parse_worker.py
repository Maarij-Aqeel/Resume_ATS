"""ARQ async worker for resume parsing."""
from __future__ import annotations

import uuid
from pathlib import Path

from arq.connections import RedisSettings
from loguru import logger
from sqlalchemy import select

from app.config import settings
from app.models.db import ParseFailure, Resume, async_session_factory
from app.pipeline.runner import run_pipeline
from app.services.embeddings import embed_resume


async def parse_resume_job(ctx, resume_id: str, file_path: str):
    """Background job: extract, parse, validate, normalize, embed, persist."""
    logger.info("worker_job_started", resume_id=resume_id, file_path=file_path)
    async with async_session_factory() as session:
        resume = await session.get(Resume, uuid.UUID(resume_id))
        if not resume:
            logger.error("worker_resume_not_found", resume_id=resume_id)
            return

        resume.parse_status = "processing"
        resume.parse_attempts += 1
        await session.commit()

        path = Path(file_path)
        if not path.exists():
            resume.parse_status = "failed"
            resume.error_message = f"file not found: {file_path}"
            await session.commit()
            return

        try:
            content = path.read_bytes()
            result = await run_pipeline(resume.original_filename, content)

            try:
                embedding = embed_resume(result.schema)
            except Exception as e:
                logger.warning("embedding_failed", error=str(e))
                embedding = None

            resume.raw_text = result.extracted.raw_text
            resume.parsed_data = result.schema.model_dump()
            resume.confidence_score = result.confidence
            resume.extractor_used = result.extracted.extractor_used
            resume.ocr_used = result.extracted.ocr_used
            resume.parse_status = (
                "completed"
                if result.confidence >= settings.MIN_CONFIDENCE_FOR_AUTO_ACCEPT
                else "review_needed"
            )
            resume.parse_time_ms = result.total_time_ms
            resume.embedding = embedding
            await session.commit()
            logger.info("worker_job_complete", resume_id=resume_id, confidence=result.confidence)

        except Exception as e:
            logger.error("worker_job_failed", resume_id=resume_id, error=str(e))
            resume.parse_status = "failed"
            resume.error_message = str(e)[:1000]
            await session.commit()

            failure = ParseFailure(
                resume_id=resume.id,
                failure_stage="pipeline",
                error_details=str(e)[:2000],
                raw_text_sample=(resume.raw_text or "")[:500],
            )
            session.add(failure)
            await session.commit()


class WorkerSettings:
    functions = [parse_resume_job]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 5
    job_timeout = 120
    max_tries = 2
    keep_result = 3600
