"""Text normalization + quality validation."""
from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_SPECIAL_CHAR_RE = re.compile(r"[^\w\s.,;:!?@#\-/()'\"&%+]")

# Heuristic keywords that strongly suggest a resume
_RESUME_KEYWORDS = (
    "experience", "education", "skills", "summary", "objective",
    "employment", "work history", "university", "college", "degree",
    "certification", "project", "engineer", "developer", "manager",
    "analyst", "intern", "consultant", "designer", "responsibilities",
)


def clean_text(text: str) -> str:
    """Collapse whitespace, strip control characters, normalize newlines."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # strip non-printable except newlines and tabs
    text = "".join(c for c in text if c == "\n" or c == "\t" or c.isprintable())
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def quality_score(text: str) -> float:
    """Score 0.0-1.0 measuring how likely this is a usable resume text."""
    if not text:
        return 0.0
    score = 0.0
    length = len(text)

    # length signal
    if length >= 500:
        score += 0.30
    elif length >= 200:
        score += 0.15
    elif length >= 100:
        score += 0.05

    # special-character ratio
    special = len(_SPECIAL_CHAR_RE.findall(text))
    special_ratio = special / max(length, 1)
    if special_ratio < 0.10:
        score += 0.20
    elif special_ratio < 0.25:
        score += 0.10

    # email presence
    if _EMAIL_RE.search(text):
        score += 0.20

    # keyword presence
    lower = text.lower()
    hits = sum(1 for kw in _RESUME_KEYWORDS if kw in lower)
    if hits >= 5:
        score += 0.30
    elif hits >= 2:
        score += 0.15
    elif hits >= 1:
        score += 0.05

    return min(score, 1.0)


def is_usable(text: str, min_length: int = 100, min_score: float = 0.30) -> bool:
    return len(text) >= min_length and quality_score(text) >= min_score
