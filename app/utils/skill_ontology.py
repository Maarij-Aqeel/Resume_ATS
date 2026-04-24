"""Skills ontology + normalization."""
from __future__ import annotations

import json
import re
import string
from functools import lru_cache
from pathlib import Path


ONTOLOGY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "skills_ontology.json"

_PUNCT_RE = re.compile(r"[^a-z0-9.+#/\- ]")


@lru_cache(maxsize=1)
def _load_ontology() -> dict:
    if not ONTOLOGY_PATH.exists():
        return {"aliases": {}, "categories": {}}
    return json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))


def _lookup_key(s: str) -> str:
    """Produce a normalized lookup key: lowercase, punctuation stripped (except '.+#/-')."""
    s = s.lower().strip()
    s = _PUNCT_RE.sub(" ", s)
    s = " ".join(s.split())
    return s


def normalize_skill(skill: str) -> str:
    """Return the canonical name for a skill string.

    Unknown skills are returned in a reasonable title-case form.
    """
    if not skill:
        return ""
    ontology = _load_ontology()
    aliases = ontology.get("aliases", {})

    raw = skill.strip()
    key = _lookup_key(raw)
    if key in aliases:
        return aliases[key]

    # try without the final 's' (e.g. 'Python scripts' -> 'python script')
    if key.endswith("s") and key[:-1] in aliases:
        return aliases[key[:-1]]

    # fallback: title-case the original, preserving common tech patterns
    return _title_case(raw)


def _title_case(s: str) -> str:
    # preserve common tech patterns (C++, C#, .NET)
    preserve = {"c++", "c#", ".net", "node.js", "react.js", "vue.js", "next.js"}
    if s.lower() in preserve:
        return {"c++": "C++", "c#": "C#", ".net": ".NET",
                "node.js": "Node.js", "react.js": "React.js",
                "vue.js": "Vue.js", "next.js": "Next.js"}[s.lower()]
    return string.capwords(s)


def normalize_skills(skills: list[str]) -> list[str]:
    """Normalize a list of skills and deduplicate (preserving order)."""
    seen: dict[str, None] = {}
    for s in skills:
        canonical = normalize_skill(s)
        if canonical and canonical not in seen:
            seen[canonical] = None
    return list(seen.keys())


def skill_category(canonical: str) -> str | None:
    """Return category for canonical skill or None."""
    return _load_ontology().get("categories", {}).get(canonical)
