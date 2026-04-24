"""Job description endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.models.db import JobDescription
from app.models.schemas import JobDescriptionIn
from app.pipeline.matcher import extract_required_skills, extract_required_years
from app.services.embeddings import embed_text

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post("/")
async def create_job(
    payload: JobDescriptionIn,
    session: AsyncSession = Depends(get_session),
):
    skills = sorted(extract_required_skills(payload))
    years = extract_required_years(payload)
    embedding = embed_text(payload.description)

    jd = JobDescription(
        id=uuid.uuid4(),
        title=payload.title,
        company=payload.company,
        description=payload.description,
        required_skills=payload.required_skills or skills,
        required_years=payload.required_years or years,
        embedding=embedding,
    )
    session.add(jd)
    await session.commit()
    return {
        "job_id": str(jd.id),
        "title": jd.title,
        "required_skills": jd.required_skills,
        "required_years": jd.required_years,
    }


@router.get("/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    jd = await session.get(JobDescription, job_id)
    if not jd:
        raise HTTPException(404, "job not found")
    return {
        "job_id": str(jd.id),
        "title": jd.title,
        "company": jd.company,
        "description": jd.description,
        "required_skills": jd.required_skills,
        "required_years": jd.required_years,
        "created_at": jd.created_at.isoformat(),
    }


@router.get("/")
async def list_jobs(
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(JobDescription).order_by(desc(JobDescription.created_at)).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "count": len(rows),
        "jobs": [
            {
                "job_id": str(j.id),
                "title": j.title,
                "company": j.company,
                "created_at": j.created_at.isoformat(),
            }
            for j in rows
        ],
    }
