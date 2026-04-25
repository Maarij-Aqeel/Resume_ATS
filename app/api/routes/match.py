"""Matching endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.models.db import JobDescription, MatchResult, Resume
from app.models.schemas import JobDescriptionIn, ResumeSchema
from app.pipeline.matcher import compute_match

router = APIRouter(prefix="/api/v1/match", tags=["match"])


@router.post("/resume/{resume_id}/job/{job_id}")
async def match_one(
    resume_id: uuid.UUID,
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    resume = await session.get(Resume, resume_id)
    job = await session.get(JobDescription, job_id)
    if not resume or not resume.parsed_data:
        raise HTTPException(404, "resume not found or not parsed")
    if not job:
        raise HTTPException(404, "job not found")
    # pgvector returns numpy arrays — use explicit None check, not truthy eval
    if resume.embedding is None or job.embedding is None:
        raise HTTPException(422, "embeddings missing — reprocess resume/job")

    schema = ResumeSchema(**resume.parsed_data)
    jd_input = JobDescriptionIn(
        title=job.title,
        company=job.company,
        description=job.description,
        required_skills=job.required_skills,
        required_years=job.required_years,
    )
    score = compute_match(schema, list(resume.embedding), jd_input, list(job.embedding))

    mr = MatchResult(
        id=uuid.uuid4(),
        resume_id=resume.id,
        job_id=job.id,
        total_score=score.total,
        score_breakdown=score.breakdown,
        matching_skills=score.matching_skills,
        missing_skills=score.missing_skills,
    )
    session.add(mr)
    await session.commit()

    return {
        "resume_id": str(resume.id),
        "job_id": str(job.id),
        "total_score": score.total,
        "breakdown": score.breakdown,
        "matching_skills": score.matching_skills,
        "missing_skills": score.missing_skills,
    }


@router.post("/job/{job_id}/top-candidates")
async def top_candidates(
    job_id: uuid.UUID,
    body: dict = Body(default={"limit": 20, "min_score": 0.0}),
    session: AsyncSession = Depends(get_session),
):
    limit = int(body.get("limit", 20))
    min_score = float(body.get("min_score", 0.0))

    job = await session.get(JobDescription, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.embedding is None:
        raise HTTPException(422, "job embedding missing")

    # pgvector ANN: sort by cosine distance against job embedding
    stmt = (
        select(Resume)
        .where(Resume.embedding.isnot(None))
        .where(Resume.parsed_data.isnot(None))
        .where(Resume.parse_status.in_(("completed", "review_needed")))
        .order_by(Resume.embedding.cosine_distance(list(job.embedding)))
        .limit(limit * 3)  # over-fetch; filter below
    )
    candidates = (await session.execute(stmt)).scalars().all()

    jd_input = JobDescriptionIn(
        title=job.title,
        company=job.company,
        description=job.description,
        required_skills=job.required_skills,
        required_years=job.required_years,
    )

    ranked: list[dict] = []
    for r in candidates:
        if r.embedding is None:
            continue
        schema = ResumeSchema(**r.parsed_data)
        score = compute_match(schema, list(r.embedding), jd_input, list(job.embedding))
        if score.total / 100 >= min_score:
            ranked.append(
                {
                    "resume_id": str(r.id),
                    "original_filename": r.original_filename,
                    "total_score": score.total,
                    "breakdown": score.breakdown,
                    "matching_skills": score.matching_skills,
                    "missing_skills": score.missing_skills,
                }
            )
    ranked.sort(key=lambda x: x["total_score"], reverse=True)
    return {"job_id": str(job.id), "count": len(ranked[:limit]), "candidates": ranked[:limit]}


@router.post("/resume/{resume_id}/top-jobs")
async def top_jobs(
    resume_id: uuid.UUID,
    body: dict = Body(default={"limit": 20, "min_score": 0.0}),
    session: AsyncSession = Depends(get_session),
):
    limit = int(body.get("limit", 20))
    min_score = float(body.get("min_score", 0.0))

    resume = await session.get(Resume, resume_id)
    if not resume or not resume.parsed_data or resume.embedding is None:
        raise HTTPException(404, "resume not found or not parsed")

    stmt = (
        select(JobDescription)
        .where(JobDescription.embedding.isnot(None))
        .order_by(JobDescription.embedding.cosine_distance(list(resume.embedding)))
        .limit(limit * 3)
    )
    candidates = (await session.execute(stmt)).scalars().all()

    schema = ResumeSchema(**resume.parsed_data)

    ranked: list[dict] = []
    for j in candidates:
        if j.embedding is None:
            continue
        jd_input = JobDescriptionIn(
            title=j.title,
            company=j.company,
            description=j.description,
            required_skills=j.required_skills,
            required_years=j.required_years,
        )
        score = compute_match(schema, list(resume.embedding), jd_input, list(j.embedding))
        if score.total / 100 >= min_score:
            ranked.append(
                {
                    "job_id": str(j.id),
                    "title": j.title,
                    "company": j.company,
                    "total_score": score.total,
                    "breakdown": score.breakdown,
                }
            )
    ranked.sort(key=lambda x: x["total_score"], reverse=True)
    return {"resume_id": str(resume.id), "count": len(ranked[:limit]), "jobs": ranked[:limit]}
