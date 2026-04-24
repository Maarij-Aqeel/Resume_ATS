"""Field-level accuracy benchmark.

Runs the full pipeline against every (resume, ground_truth) pair in
tests/accuracy/fixtures/ and prints field-level accuracy metrics.

Usage:
    pytest tests/accuracy/ --benchmark
    python -m tests.accuracy.benchmark           # standalone
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.pipeline.runner import run_pipeline
from tests.accuracy.metrics import (
    count_match,
    date_match,
    exact_match,
    experience_dates_f1,
    f1_score,
    fuzzy_match,
    normalized_match,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# Per-field target thresholds
TARGETS = {
    "name_accuracy": 0.98,
    "email_accuracy": 0.99,
    "phone_accuracy": 0.95,
    "skills_f1": 0.90,
    "experience_count": 0.95,
    "experience_dates": 0.92,
    "education_accuracy": 0.95,
    "title_accuracy": 0.90,
    "overall_accuracy": 0.95,
}


def _iter_fixtures() -> list[tuple[Path, Path]]:
    """Find every resume file that has a matching .gt.json ground truth."""
    pairs: list[tuple[Path, Path]] = []
    if not FIXTURES_DIR.exists():
        return pairs
    for gt in FIXTURES_DIR.glob("*.gt.json"):
        stem = gt.name[:-8]  # strip .gt.json
        for ext in ("pdf", "docx", "doc", "txt"):
            resume = FIXTURES_DIR / f"{stem}.{ext}"
            if resume.exists():
                pairs.append((resume, gt))
                break
    return pairs


async def _run_one(resume_path: Path, gt_path: Path) -> dict:
    content = resume_path.read_bytes()
    ground = json.loads(gt_path.read_text())

    result = await run_pipeline(resume_path.name, content)
    parsed = result.schema.model_dump()

    return {
        "resume": resume_path.name,
        "expected": ground,
        "actual": parsed,
        "confidence": result.confidence,
    }


def _score_fields(expected: dict, actual: dict) -> dict:
    exp_personal = expected.get("personal_info", {}) or {}
    act_personal = actual.get("personal_info", {}) or {}

    scores = {
        "name":       1.0 if exact_match(exp_personal.get("full_name"), act_personal.get("full_name")) else 0.0,
        "email":      1.0 if exact_match(exp_personal.get("email"), act_personal.get("email")) else 0.0,
        "phone":      1.0 if normalized_match(exp_personal.get("phone"), act_personal.get("phone")) else 0.0,
    }

    exp_skills = (expected.get("skills", {}) or {}).get("technical", [])
    act_skills = (actual.get("skills", {}) or {}).get("technical", [])
    scores["skills_f1"] = f1_score(exp_skills, act_skills)

    exp_exp = expected.get("experience", []) or []
    act_exp = actual.get("experience", []) or []
    scores["experience_count"] = 1.0 if count_match(len(exp_exp), len(act_exp)) else 0.0
    scores["experience_dates"] = experience_dates_f1(exp_exp, act_exp)

    exp_edu = expected.get("education", []) or []
    act_edu = actual.get("education", []) or []
    # education exact match = same count AND same institution names
    if len(exp_edu) == len(act_edu):
        exp_inst = sorted([(e.get("institution_name") or "").lower() for e in exp_edu])
        act_inst = sorted([(e.get("institution_name") or "").lower() for e in act_edu])
        scores["education"] = 1.0 if exp_inst == act_inst else 0.0
    else:
        scores["education"] = 0.0

    # Title accuracy: last (first in list) title fuzzy match
    exp_title = exp_exp[0].get("job_title") if exp_exp else None
    act_title = act_exp[0].get("job_title") if act_exp else None
    scores["title"] = 1.0 if fuzzy_match(exp_title, act_title, 0.90) else 0.0

    return scores


def aggregate(per_resume: list[dict]) -> dict:
    if not per_resume:
        return {k: 0.0 for k in TARGETS}
    n = len(per_resume)
    aggregate_scores = {k: 0.0 for k in ("name", "email", "phone", "skills_f1", "experience_count", "experience_dates", "education", "title")}
    for row in per_resume:
        s = row["scores"]
        for k in aggregate_scores:
            aggregate_scores[k] += s.get(k, 0.0)
    for k in aggregate_scores:
        aggregate_scores[k] /= n

    # Weighted overall
    weights = {
        "name":             0.15,
        "email":            0.15,
        "phone":            0.10,
        "skills_f1":        0.15,
        "experience_count": 0.15,
        "experience_dates": 0.10,
        "education":        0.10,
        "title":            0.10,
    }
    overall = sum(aggregate_scores[k] * w for k, w in weights.items())

    return {
        "name_accuracy": aggregate_scores["name"],
        "email_accuracy": aggregate_scores["email"],
        "phone_accuracy": aggregate_scores["phone"],
        "skills_f1": aggregate_scores["skills_f1"],
        "experience_count": aggregate_scores["experience_count"],
        "experience_dates": aggregate_scores["experience_dates"],
        "education_accuracy": aggregate_scores["education"],
        "title_accuracy": aggregate_scores["title"],
        "overall_accuracy": overall,
    }


async def run_benchmark() -> dict:
    pairs = _iter_fixtures()
    if not pairs:
        return {"count": 0, "metrics": {}, "detail": []}

    per_resume = []
    for resume_path, gt_path in pairs:
        row = await _run_one(resume_path, gt_path)
        row["scores"] = _score_fields(row["expected"], row["actual"])
        per_resume.append(row)

    metrics = aggregate(per_resume)
    return {
        "count": len(pairs),
        "metrics": metrics,
        "detail": [
            {"resume": r["resume"], "scores": r["scores"], "confidence": r["confidence"]}
            for r in per_resume
        ],
    }


@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_benchmark_meets_targets():
    report = await run_benchmark()
    if report["count"] == 0:
        pytest.skip("no fixtures present — place resume+.gt.json pairs in tests/accuracy/fixtures")

    metrics = report["metrics"]
    print("\n\n=== Accuracy Report ===")
    for k, v in metrics.items():
        target = TARGETS.get(k)
        flag = "✓" if (target is None or v >= target) else "✗"
        print(f"  {flag} {k}: {v:.3f} (target {target})")

    failures = [
        f"{k}={v:.3f} < {target}"
        for k, v in metrics.items()
        if (target := TARGETS.get(k)) is not None and v < target
    ]
    assert not failures, f"Accuracy targets missed: {failures}"


if __name__ == "__main__":
    report = asyncio.run(run_benchmark())
    print(json.dumps(report, indent=2, default=str))
