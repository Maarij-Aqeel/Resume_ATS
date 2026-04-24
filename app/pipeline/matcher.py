"""Layer 5: semantic matching between resumes and job descriptions."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.models.schemas import JobDescriptionIn, MatchScore, ResumeSchema
from app.services.embeddings import cosine_similarity, embed_text
from app.utils.skill_ontology import normalize_skills


_YEARS_RE = re.compile(r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)?", re.IGNORECASE)


def extract_required_skills(jd: JobDescriptionIn) -> set[str]:
    """Normalize user-provided required_skills, else try to harvest from description."""
    if jd.required_skills:
        return set(normalize_skills(jd.required_skills))
    # Heuristic fallback: match against known ontology keywords in the description
    from app.utils.skill_ontology import _load_ontology

    ontology = _load_ontology()
    aliases = ontology.get("aliases", {})
    text = jd.description.lower()
    found: set[str] = set()
    for alias, canonical in aliases.items():
        # word-boundary match — guard multi-word aliases
        if alias in text:
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, text):
                found.add(canonical)
    return found


def extract_required_years(jd: JobDescriptionIn) -> int:
    if jd.required_years is not None:
        return jd.required_years
    m = _YEARS_RE.search(jd.description)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return 0


def _education_match(education, jd_text: str) -> float:
    """Check if required degree level is met."""
    if not education:
        return 0.0

    jd_lower = jd_text.lower()
    required_level = None
    if "phd" in jd_lower or "doctorate" in jd_lower or "doctoral" in jd_lower:
        required_level = "PhD"
    elif "master" in jd_lower or "m.s." in jd_lower or "ms degree" in jd_lower:
        required_level = "Master"
    elif "bachelor" in jd_lower or "b.s." in jd_lower or "bs degree" in jd_lower or "undergraduate" in jd_lower:
        required_level = "Bachelor"

    hierarchy = {
        "High School": 0,
        "Certificate": 1,
        "Diploma": 1,
        "Associate": 2,
        "Bachelor": 3,
        "Master": 4,
        "PhD": 5,
    }

    if required_level is None:
        # No explicit requirement → any education counts
        return 1.0

    required_rank = hierarchy[required_level]
    top_rank = max(
        (hierarchy.get(e.degree_type or "", 0) for e in education),
        default=0,
    )
    if top_rank >= required_rank:
        return 1.0
    return 0.5  # partial credit


def _title_similarity(resume_title: str | None, jd_title: str) -> float:
    if not resume_title:
        return 0.0
    return SequenceMatcher(None, resume_title.lower(), jd_title.lower()).ratio()


def compute_match(
    resume: ResumeSchema,
    resume_embedding: list[float],
    jd: JobDescriptionIn,
    jd_embedding: list[float] | None = None,
) -> MatchScore:
    """Compute a weighted multi-factor match score."""
    if jd_embedding is None:
        jd_embedding = embed_text(jd.description)

    # 1. Semantic similarity (40%)
    semantic = max(0.0, cosine_similarity(resume_embedding, jd_embedding))

    # 2. Skill match (30%)
    required_skills = extract_required_skills(jd)
    resume_skills = set(normalize_skills(resume.skills.technical + resume.skills.tools))
    if required_skills:
        matching = required_skills & resume_skills
        missing = required_skills - resume_skills
        skill_score = len(matching) / len(required_skills)
    else:
        matching = set()
        missing = set()
        skill_score = 0.5  # no requirements → neutral

    # 3. Experience years (15%)
    required_years = extract_required_years(jd)
    total_years = resume.parser_metadata.total_years_experience or 0
    if required_years > 0:
        experience_score = min(total_years / required_years, 1.0)
    else:
        experience_score = 1.0

    # 4. Education (10%)
    education_score = _education_match(resume.education, jd.description)

    # 5. Title similarity (5%)
    last_title = resume.experience[0].job_title if resume.experience else None
    title_score = _title_similarity(last_title, jd.title)

    final = (
        semantic * 0.40
        + skill_score * 0.30
        + experience_score * 0.15
        + education_score * 0.10
        + title_score * 0.05
    )

    return MatchScore(
        total=round(final * 100, 1),
        breakdown={
            "semantic": round(semantic, 3),
            "skills": round(skill_score, 3),
            "experience": round(experience_score, 3),
            "education": round(education_score, 3),
            "title": round(title_score, 3),
        },
        matching_skills=sorted(matching),
        missing_skills=sorted(missing),
    )
