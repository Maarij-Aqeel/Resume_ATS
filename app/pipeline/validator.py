"""Layer 3: Pydantic validation + confidence scoring."""
from __future__ import annotations

from loguru import logger

from app.models.schemas import (
    Education,
    Experience,
    PersonalInfo,
    ResumeSchema,
    Skills,
)


def validate_parsed(parsed: dict) -> ResumeSchema:
    """Validate the raw LLM dict into a ResumeSchema. Invalid entries are dropped, not errored out."""
    # Best-effort: normalize null-like values before pydantic validation
    cleaned = _clean_nulls(parsed)

    try:
        schema = ResumeSchema(**cleaned)
    except Exception as e:
        logger.warning("schema_validation_failed_attempting_partial", error=str(e))
        schema = _partial_validate(cleaned)

    return schema


def _clean_nulls(obj):
    """Recursively replace 'N/A', 'null', '' with None."""
    if isinstance(obj, dict):
        return {k: _clean_nulls(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nulls(v) for v in obj if v not in (None, "", "N/A", "null")]
    if isinstance(obj, str):
        s = obj.strip()
        if s.lower() in ("n/a", "null", "none", ""):
            return None
        return s
    return obj


def _partial_validate(cleaned: dict) -> ResumeSchema:
    """Build the schema section-by-section, dropping sections that fail validation."""
    result = ResumeSchema()

    personal = cleaned.get("personal_info") or {}
    try:
        result.personal_info = PersonalInfo(**personal)
    except Exception as e:
        logger.warning("personal_info_invalid", error=str(e))

    result.professional_summary = cleaned.get("professional_summary")

    try:
        result.skills = Skills(**(cleaned.get("skills") or {}))
    except Exception as e:
        logger.warning("skills_invalid", error=str(e))

    for exp in cleaned.get("experience") or []:
        try:
            result.experience.append(Experience(**exp))
        except Exception as e:
            logger.warning("experience_entry_invalid", error=str(e), entry=exp)

    for edu in cleaned.get("education") or []:
        try:
            result.education.append(Education(**edu))
        except Exception as e:
            logger.warning("education_entry_invalid", error=str(e), entry=edu)

    # Sections below use lenient catch-and-continue
    for key, cls_name in (
        ("certifications", "Certification"),
        ("projects", "Project"),
        ("awards", "Award"),
        ("publications", "Publication"),
        ("volunteer_experience", "Volunteer"),
        ("languages_spoken", "LanguageSpoken"),
    ):
        from app.models import schemas as s
        cls = getattr(s, cls_name)
        for item in cleaned.get(key) or []:
            try:
                getattr(result, key).append(cls(**item))
            except Exception as e:
                logger.warning(f"{key}_entry_invalid", error=str(e))

    try:
        from app.models.schemas import ParserMetadata
        result.parser_metadata = ParserMetadata(**(cleaned.get("parser_metadata") or {}))
    except Exception:
        pass

    return result


def compute_confidence(schema: ResumeSchema) -> float:
    """Compute a 0-1 confidence score based on field coverage + validity."""
    score = 0.0

    weights = {
        "full_name":    0.15,
        "email":        0.15,
        "phone":        0.10,
        "experience":   0.25,
        "education":    0.15,
        "skills":       0.15,
        "dates_valid":  0.05,
    }

    if schema.personal_info.full_name:
        score += weights["full_name"]
    if schema.personal_info.email:
        score += weights["email"]
    if schema.personal_info.phone:
        score += weights["phone"]

    # Experience: at least one entry with company + title
    good_exp = any(
        e.company_name and e.job_title for e in schema.experience
    )
    if good_exp:
        score += weights["experience"]
    elif schema.experience:
        score += weights["experience"] * 0.5

    if schema.education:
        score += weights["education"]

    if len(schema.skills.technical) >= 3:
        score += weights["skills"]
    elif schema.skills.technical:
        score += weights["skills"] * 0.5

    # Date validity: count how many experience entries have proper start_date
    if schema.experience:
        with_dates = sum(1 for e in schema.experience if e.start_date)
        if with_dates / len(schema.experience) >= 0.8:
            score += weights["dates_valid"]

    return round(min(score, 1.0), 3)
