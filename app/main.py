"""FastAPI entry point."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from loguru import logger

from app.api.routes import jobs, match, metrics, resumes
from app.config import settings


# configure loguru
logger.remove()
logger.add(sys.stdout, serialize=False, level="INFO")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_api", model=settings.LLM_MODEL)
    # arq redis pool for enqueueing
    try:
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        logger.info("arq_pool_ready")
    except Exception as e:
        logger.warning("arq_pool_unavailable", error=str(e))
        app.state.arq_pool = None
    yield
    if app.state.arq_pool is not None:
        await app.state.arq_pool.close()


app = FastAPI(
    title="ATS Resume Parser",
    version="1.0.0",
    description="LLM-first resume parser targeting ≥95% field-level extraction accuracy.",
    lifespan=lifespan,
)

app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(match.router)
app.include_router(metrics.router)


@app.get("/")
async def root():
    return {
        "name": "ATS Resume Parser",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
