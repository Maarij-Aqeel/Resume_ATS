"""Metrics endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.models.db import Resume

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@router.get("/accuracy")
async def accuracy_stats(session: AsyncSession = Depends(get_session)):
    # Count resumes by status
    total = (await session.execute(select(func.count(Resume.id)))).scalar() or 0
    if total == 0:
        return {
            "total": 0,
            "avg_confidence": None,
            "low_confidence_count": 0,
            "failed_count": 0,
            "ocr_usage_rate": 0.0,
        }

    avg_conf = (await session.execute(
        select(func.avg(Resume.confidence_score)).where(Resume.confidence_score.isnot(None))
    )).scalar()
    low_conf = (await session.execute(
        select(func.count(Resume.id)).where(Resume.confidence_score < 0.70)
    )).scalar() or 0
    failed = (await session.execute(
        select(func.count(Resume.id)).where(Resume.parse_status == "failed")
    )).scalar() or 0
    ocr = (await session.execute(
        select(func.count(Resume.id)).where(Resume.ocr_used.is_(True))
    )).scalar() or 0

    return {
        "total": total,
        "avg_confidence": float(avg_conf) if avg_conf is not None else None,
        "low_confidence_count": low_conf,
        "failed_count": failed,
        "ocr_usage_rate": round(ocr / total, 3),
    }
