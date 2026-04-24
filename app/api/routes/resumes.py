"""Resume endpoints."""
from __future__ import annotations

import uuid
from pathlib import Path

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.config import settings
from app.models.db import Resume
from app.models.schemas import ResumeFull, ResumeStatus
from app.pipeline.runner import run_pipeline
from app.services.embeddings import embed_resume

router = APIRouter(prefix="/api/v1/resumes", tags=["resumes"])

SUPPORTED_TYPES = {"pdf", "docx", "doc", "txt", "rtf"}


async def _get_arq(request: Request) -> ArqRedis | None:
    """Return the ARQ pool from app.state if present."""
    return getattr(request.app.state, "arq_pool", None)


@router.post("/upload", status_code=202)
async def upload_resume_async(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Async upload: enqueue parse job, return resume_id."""
    content = await file.read()
    _validate_upload(file.filename or "", content)

    resume = Resume(
        id=uuid.uuid4(),
        original_filename=file.filename or "upload",
        file_type=Path(file.filename or "").suffix.lower().lstrip(".") or "unknown",
        file_size_bytes=len(content),
        parse_status="pending",
    )
    session.add(resume)
    await session.commit()

    # Persist file to disk so worker can read it
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_path = upload_dir / f"{resume.id}{Path(file.filename or '.bin').suffix}"
    saved_path.write_bytes(content)

    pool = await _get_arq(request)
    if pool is None:
        raise HTTPException(503, "async worker pool not configured")
    await pool.enqueue_job("parse_resume_job", str(resume.id), str(saved_path))

    return {"resume_id": str(resume.id), "status": "processing"}


@router.post("/upload/sync")
async def upload_resume_sync(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Synchronous upload — waits for parse result. Only use for small resumes."""
    content = await file.read()
    _validate_upload(file.filename or "", content)

    resume_id = uuid.uuid4()
    try:
        result = await run_pipeline(file.filename or "upload", content)
    except Exception as e:
        logger.error("sync_parse_failed", error=str(e))
        raise HTTPException(422, f"Parsing failed: {e}")

    embedding = None
    try:
        embedding = embed_resume(result.schema)
    except Exception as e:
        logger.warning("embedding_failed", error=str(e))

    resume = Resume(
        id=resume_id,
        original_filename=file.filename or "upload",
        file_type=result.extracted.file_type,
        file_size_bytes=len(content),
        raw_text=result.extracted.raw_text,
        parsed_data=result.schema.model_dump(),
        confidence_score=result.confidence,
        extractor_used=result.extracted.extractor_used,
        ocr_used=result.extracted.ocr_used,
        parse_status="completed" if result.confidence >= settings.MIN_CONFIDENCE_FOR_AUTO_ACCEPT else "review_needed",
        parse_attempts=result.parse_attempts,
        parse_time_ms=result.total_time_ms,
        embedding=embedding,
    )
    session.add(resume)
    await session.commit()

    return ResumeFull(
        resume_id=str(resume_id),
        status=resume.parse_status,
        confidence_score=result.confidence,
        parsed_data=result.schema,
        original_filename=resume.original_filename,
        file_type=resume.file_type,
        extractor_used=resume.extractor_used,
        ocr_used=resume.ocr_used,
    )


@router.get("/{resume_id}", response_model=ResumeFull)
async def get_resume(
    resume_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    resume = await session.get(Resume, resume_id)
    if not resume:
        raise HTTPException(404, "resume not found")
    from app.models.schemas import ResumeSchema

    parsed = ResumeSchema(**resume.parsed_data) if resume.parsed_data else None
    return ResumeFull(
        resume_id=str(resume.id),
        status=resume.parse_status,
        confidence_score=float(resume.confidence_score) if resume.confidence_score is not None else None,
        parsed_data=parsed,
        original_filename=resume.original_filename,
        file_type=resume.file_type or "unknown",
        extractor_used=resume.extractor_used,
        ocr_used=resume.ocr_used,
    )


@router.get("/{resume_id}/status", response_model=ResumeStatus)
async def get_status(
    resume_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    resume = await session.get(Resume, resume_id)
    if not resume:
        raise HTTPException(404, "resume not found")
    return ResumeStatus(
        resume_id=str(resume.id),
        status=resume.parse_status,
        confidence_score=float(resume.confidence_score) if resume.confidence_score is not None else None,
        parse_time_ms=resume.parse_time_ms,
        error_message=resume.error_message,
    )


@router.get("/")
async def list_resumes(
    status: str | None = Query(None),
    min_confidence: float | None = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Resume).order_by(desc(Resume.created_at))
    if status:
        stmt = stmt.where(Resume.parse_status == status)
    if min_confidence is not None:
        stmt = stmt.where(Resume.confidence_score >= min_confidence)
    stmt = stmt.offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "count": len(rows),
        "offset": offset,
        "limit": limit,
        "resumes": [
            {
                "resume_id": str(r.id),
                "original_filename": r.original_filename,
                "status": r.parse_status,
                "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    resume = await session.get(Resume, resume_id)
    if not resume:
        raise HTTPException(404, "resume not found")
    await session.delete(resume)
    await session.commit()
    return {"deleted": str(resume_id)}


def _validate_upload(filename: str, content: bytes):
    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"file exceeds {settings.MAX_FILE_SIZE_MB}MB limit")
    if not content:
        raise HTTPException(400, "empty file")
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_TYPES:
        raise HTTPException(415, f"unsupported file type '{ext}'; supported: {sorted(SUPPORTED_TYPES)}")
