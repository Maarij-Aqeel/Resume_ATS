"""Date normalization for every resume-style format."""
from __future__ import annotations

import re
from datetime import datetime

import dateparser


_PRESENT_TOKENS = {
    "present", "current", "now", "ongoing", "till date", "to date",
    "till now", "presently", "till present", "-present", "– present",
    "—present", "currently",
}

_QUARTER_MONTH = {"q1": 1, "q2": 4, "q3": 7, "q4": 10}
_SEASON_MONTH = {
    "spring": 3, "summer": 6, "fall": 9, "autumn": 9, "winter": 12,
}

_YEAR_ONLY_RE = re.compile(r"^\s*(\d{4})\s*$")
_QUARTER_RE = re.compile(r"^\s*(q[1-4])\s+(\d{4})\s*$", re.IGNORECASE)
_SEASON_RE = re.compile(r"^\s*(spring|summer|fall|autumn|winter)\s+(\d{4})\s*$", re.IGNORECASE)


def normalize_date(raw: str | None) -> tuple[str | None, bool]:
    """
    Normalize a free-form date string to 'YYYY-MM' format.

    Returns (normalized_date_or_None, is_current_flag).
    is_current=True means the date represents Present/Now/Current.
    """
    if raw is None:
        return None, False
    s = str(raw).strip().lower()
    if not s:
        return None, False

    if s in _PRESENT_TOKENS or any(t in s for t in ("present", "current", "ongoing", "now")):
        return None, True

    q = _QUARTER_RE.match(s)
    if q:
        month = _QUARTER_MONTH[q.group(1).lower()]
        year = int(q.group(2))
        return f"{year:04d}-{month:02d}", False

    sea = _SEASON_RE.match(s)
    if sea:
        month = _SEASON_MONTH[sea.group(1).lower()]
        year = int(sea.group(2))
        return f"{year:04d}-{month:02d}", False

    y = _YEAR_ONLY_RE.match(s)
    if y:
        year = int(y.group(1))
        return f"{year:04d}-01", False

    # dateparser handles "Jan 2021", "January 2021", "Jan '21", "01/2021", "2021-01", etc.
    parsed = dateparser.parse(raw, settings={"PREFER_DAY_OF_MONTH": "first"})
    if parsed is not None:
        # Sanity check: year must be reasonable
        if 1950 <= parsed.year <= datetime.utcnow().year + 1:
            return f"{parsed.year:04d}-{parsed.month:02d}", False

    return None, False


def months_between(start: str | None, end: str | None) -> int:
    """Compute inclusive months between two YYYY-MM dates. Missing end = now."""
    if not start:
        return 0
    try:
        sy, sm = map(int, start.split("-"))
    except (ValueError, AttributeError):
        return 0
    if end:
        try:
            ey, em = map(int, end.split("-"))
        except (ValueError, AttributeError):
            now = datetime.utcnow()
            ey, em = now.year, now.month
    else:
        now = datetime.utcnow()
        ey, em = now.year, now.month
    months = (ey - sy) * 12 + (em - sm)
    return max(months, 0)
