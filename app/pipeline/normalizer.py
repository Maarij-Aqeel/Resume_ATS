"""Layer 4: normalization — skills, dates, experience totals."""
from __future__ import annotations

from datetime import datetime

from loguru import logger

from app.models.schemas import ResumeSchema
from app.utils.date_parser import months_between, normalize_date
from app.utils.skill_ontology import normalize_skills


def normalize_resume(schema: ResumeSchema) -> ResumeSchema:
    """Normalize skills, dates, and compute total experience in place."""
    # Skills
    schema.skills.technical = normalize_skills(schema.skills.technical)
    schema.skills.soft = normalize_skills(schema.skills.soft)
    schema.skills.tools = normalize_skills(schema.skills.tools)
    # Languages in skills should stay as language names; normalize still dedupes
    schema.skills.languages = normalize_skills(schema.skills.languages)
    schema.skills.certifications_mentioned_as_skills = normalize_skills(
        schema.skills.certifications_mentioned_as_skills
    )

    # Experience entries
    for exp in schema.experience:
        exp.skills_mentioned = normalize_skills(exp.skills_mentioned)

        start_norm, start_current = normalize_date(exp.start_date)
        end_norm, end_current = normalize_date(exp.end_date)
        if start_norm:
            exp.start_date = start_norm
        if end_norm:
            exp.end_date = end_norm
        elif end_current:
            exp.end_date = None
            exp.is_current = True
        if start_current:
            # unusual but possible ("Present" in start?) - flag current
            exp.is_current = True

    # Education entries
    for edu in schema.education:
        start_norm, _ = normalize_date(edu.start_date)
        end_norm, end_current = normalize_date(edu.graduation_date)
        if start_norm:
            edu.start_date = start_norm
        if end_norm:
            edu.graduation_date = end_norm
        elif end_current:
            edu.graduation_date = None
            edu.is_ongoing = True

    # Projects
    for proj in schema.projects:
        proj.technologies = normalize_skills(proj.technologies)
        start_norm, _ = normalize_date(proj.start_date)
        end_norm, end_current = normalize_date(proj.end_date)
        if start_norm:
            proj.start_date = start_norm
        if end_norm:
            proj.end_date = end_norm
        elif end_current:
            proj.end_date = None

    # Certifications
    for cert in schema.certifications:
        iss_norm, _ = normalize_date(cert.issue_date)
        exp_norm, _ = normalize_date(cert.expiry_date)
        if iss_norm:
            cert.issue_date = iss_norm
        if exp_norm:
            cert.expiry_date = exp_norm

    # Total years of experience
    schema.parser_metadata.total_years_experience = _compute_total_experience(schema)

    # Infer career level if missing
    if not schema.parser_metadata.career_level and schema.parser_metadata.total_years_experience is not None:
        schema.parser_metadata.career_level = _infer_career_level(
            schema.parser_metadata.total_years_experience, schema.experience
        )

    return schema


def _compute_total_experience(schema: ResumeSchema) -> float | None:
    if not schema.experience:
        return None
    total_months = 0
    for exp in schema.experience:
        total_months += months_between(exp.start_date, exp.end_date)
    return round(total_months / 12, 1)


def _infer_career_level(years: float, experience: list) -> str:
    titles = " ".join((e.job_title or "").lower() for e in experience)
    if any(kw in titles for kw in ("cto", "cfo", "ceo", "vp", "chief", "president")):
        return "Executive"
    if "director" in titles:
        return "Director"
    if "manager" in titles or "head of" in titles:
        return "Manager"
    if "lead" in titles or "principal" in titles:
        return "Lead"
    if years >= 8:
        return "Senior"
    if years >= 4:
        return "Mid"
    if years >= 2:
        return "Junior"
    return "Entry"
