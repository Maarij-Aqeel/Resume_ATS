"""Embeddings via fastembed (ONNX runtime — no torch)."""
from __future__ import annotations

from functools import lru_cache

from loguru import logger

from app.config import settings
from app.models.schemas import ResumeSchema

# fastembed model names include a vendor prefix. Map the friendly name used in
# settings.EMBEDDING_MODEL to the fastembed canonical name.
_FASTEMBED_MODEL_MAP = {
    "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
}


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding

    name = _FASTEMBED_MODEL_MAP.get(settings.EMBEDDING_MODEL, settings.EMBEDDING_MODEL)
    logger.info("loading_embedding_model", model=name)
    # fastembed downloads the ONNX weights to ~/.cache on first use (~20 MB)
    return TextEmbedding(model_name=name)


def _build_resume_text(schema: ResumeSchema) -> str:
    """Flatten the relevant parts of a parsed resume into an embedding-friendly string."""
    parts: list[str] = []

    if schema.personal_info.full_name:
        parts.append(schema.personal_info.full_name)
    if schema.professional_summary:
        parts.append(schema.professional_summary)

    if schema.skills.technical:
        parts.append("Skills: " + ", ".join(schema.skills.technical))
    if schema.skills.tools:
        parts.append("Tools: " + ", ".join(schema.skills.tools))

    for exp in schema.experience[:10]:
        if exp.job_title:
            parts.append(f"Title: {exp.job_title}")
        if exp.company_name:
            parts.append(f"Company: {exp.company_name}")
        if exp.description:
            parts.append(exp.description[:500])

    for edu in schema.education:
        if edu.degree_type and edu.field_of_study:
            parts.append(f"{edu.degree_type} in {edu.field_of_study}")
        if edu.institution_name:
            parts.append(edu.institution_name)

    return "\n".join(parts)


def embed_resume(schema: ResumeSchema) -> list[float]:
    text = _build_resume_text(schema)
    if not text:
        return [0.0] * 384
    # fastembed returns a generator of numpy arrays; take the first
    vector = next(iter(_model().embed([text])))
    return vector.tolist()


def embed_text(text: str) -> list[float]:
    if not text:
        return [0.0] * 384
    vector = next(iter(_model().embed([text])))
    return vector.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
