# Skill loader — scans bundled and user skill directories, selects the best
# matching skill for a given matter type, and returns its full content.
#
# WHY two directories:
#   Bundled (lexagent/skills/)    — ships with the package, versioned in git
#   User (~/.lexagent/skills/)    — lawyer-editable without touching code
#   User skills with the same `name` as a bundled skill win (override).

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple, Optional

import yaml


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class SkillMatch(NamedTuple):
    """Return type for load_skill_with_tier(). Separates body from tier metadata."""
    body: str
    min_tier: int


def load_skill_with_tier(
    matter_type: str,
    bundled_skills_dir: str | Path,
    user_skills_dir: str | Path,
) -> Optional[SkillMatch]:
    """
    Like load_skill() but returns a SkillMatch(body, min_tier) instead of a plain str.

    min_tier is read from the skill YAML frontmatter field `min_inference_tier`
    (default 4 if absent). Callers can enforce the tier before injecting the body.

    WHY a separate function instead of changing load_skill():
      load_skill() returns Optional[str] and 11 existing tests depend on that.
      Changing the return type would break all of them. This parallel function
      gives new callers tier metadata without touching the original API.
    """
    if not matter_type or not matter_type.strip():
        return None

    bundled = _skills_from_dir(Path(bundled_skills_dir))
    user = _skills_from_dir(Path(str(user_skills_dir)).expanduser())

    by_name: dict[str, dict] = {}
    for skill in bundled:
        if skill["name"]:
            by_name[skill["name"]] = skill
    for skill in user:
        if skill["name"]:
            by_name[skill["name"]] = skill

    skills = list(by_name.values())
    normalised = _normalise(matter_type)

    for skill in skills:
        if normalised in [_normalise(mt) for mt in skill["matter_types"]]:
            return SkillMatch(body=skill["body"], min_tier=skill["min_tier"])

    for skill in skills:
        for kw in skill["trigger_keywords"]:
            if kw.lower() in matter_type.lower():
                return SkillMatch(body=skill["body"], min_tier=skill["min_tier"])

    return None


def load_skill(
    matter_type: str,
    bundled_skills_dir: str | Path,
    user_skills_dir: str | Path,
) -> Optional[str]:
    """
    Find and return the content of the best-matching skill for matter_type.

    Matching priority (first match wins):
      1. matter_types exact match  (normalised: lowercase, spaces → underscores)
      2. trigger_keywords substring match (case-insensitive)

    User skills with the same `name` override bundled skills.
    Returns None if no skill matches.
    """
    if not matter_type or not matter_type.strip():
        return None

    # Build the merged skill list: bundled first, then user (user wins on name clash)
    bundled = _skills_from_dir(Path(bundled_skills_dir))
    user = _skills_from_dir(Path(str(user_skills_dir)).expanduser())

    # User skills override bundled by name — build a dict keyed by name, user last
    by_name: dict[str, dict] = {}
    for skill in bundled:
        if skill["name"]:
            by_name[skill["name"]] = skill
    for skill in user:
        if skill["name"]:
            by_name[skill["name"]] = skill  # overwrites bundled if same name

    skills = list(by_name.values())

    normalised = _normalise(matter_type)

    # Pass 1: exact match on matter_types list
    for skill in skills:
        if normalised in [_normalise(mt) for mt in skill["matter_types"]]:
            return skill["body"]

    # Pass 2: any trigger_keyword is a substring of matter_type
    for skill in skills:
        for kw in skill["trigger_keywords"]:
            if kw.lower() in matter_type.lower():
                return skill["body"]

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _skills_from_dir(directory: Path) -> list[dict]:
    """Return parsed skill dicts for every .md file in directory."""
    if not directory.exists() or not directory.is_dir():
        return []
    skills = []
    for md_file in directory.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        parsed = _parse_frontmatter(content)
        skills.append(parsed)
    return skills


def _parse_frontmatter(content: str) -> dict:
    """
    Parse YAML frontmatter from a skill .md file.

    Returns a dict with: name, trigger_keywords, matter_types, body (rest of file).
    If no frontmatter is found, returns empty metadata with the full content as body.
    """
    # YAML frontmatter is delimited by --- on its own line at start and end
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return {"name": "", "trigger_keywords": [], "matter_types": [], "body": content}

    raw_yaml = match.group(1)
    body = match.group(2).strip()

    try:
        meta = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError:
        meta = {}

    return {
        "name": str(meta.get("name", "")),
        "trigger_keywords": _as_list(meta.get("trigger_keywords", [])),
        "matter_types": _as_list(meta.get("matter_types", [])),
        "body": body,
        "min_tier": int(meta.get("min_inference_tier", 4)),
    }


def _normalise(text: str) -> str:
    """Lowercase + replace spaces/hyphens with underscores for comparison."""
    return re.sub(r"[\s\-]+", "_", text.strip().lower())


def _as_list(value) -> list[str]:
    """Accept either a YAML list or a comma-separated string; always return list."""
    if isinstance(value, list):
        return [str(v).strip() for v in value]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []
