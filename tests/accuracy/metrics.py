"""Field-level accuracy metrics for benchmarking."""
from __future__ import annotations

from difflib import SequenceMatcher

import phonenumbers


def exact_match(expected, actual) -> bool:
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    return str(expected).strip().lower() == str(actual).strip().lower()


def fuzzy_match(expected, actual, threshold: float = 0.90) -> bool:
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    ratio = SequenceMatcher(None, str(expected).lower(), str(actual).lower()).ratio()
    return ratio >= threshold


def normalized_match(expected, actual) -> bool:
    """Phone-number aware match."""
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False

    def norm(n):
        try:
            parsed = phonenumbers.parse(str(n), "US")
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass
        return "".join(c for c in str(n) if c.isdigit())

    return norm(expected) == norm(actual)


def f1_score(expected: list[str], actual: list[str]) -> float:
    if not expected and not actual:
        return 1.0
    exp_set = {s.strip().lower() for s in expected}
    act_set = {s.strip().lower() for s in actual}
    if not exp_set or not act_set:
        return 0.0
    tp = len(exp_set & act_set)
    if tp == 0:
        return 0.0
    precision = tp / len(act_set)
    recall = tp / len(exp_set)
    return 2 * precision * recall / (precision + recall)


def count_match(expected_count: int, actual_count: int) -> bool:
    return expected_count == actual_count


def date_match(expected: str | None, actual: str | None, tolerance_months: int = 1) -> bool:
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    try:
        ey, em = map(int, expected.split("-"))
        ay, am = map(int, actual.split("-"))
        diff = abs((ey - ay) * 12 + (em - am))
        return diff <= tolerance_months
    except (ValueError, AttributeError):
        return False


def experience_dates_f1(expected: list[dict], actual: list[dict]) -> float:
    """Compare experience entries on (company_name + start_date) match."""
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0

    matched = 0
    for e in expected:
        for a in actual:
            if (
                exact_match(e.get("company_name"), a.get("company_name"))
                and date_match(e.get("start_date"), a.get("start_date"))
            ):
                matched += 1
                break

    if matched == 0:
        return 0.0
    precision = matched / len(actual)
    recall = matched / len(expected)
    return 2 * precision * recall / (precision + recall)
