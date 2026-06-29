# Skill loader — scans bundled and user skill directories, selects the best
# matching skill for a given matter type, and returns its full content.
#
# WHY two directories:
#   Bundled (themis/skills/)    — ships with the package, versioned in git
#   User (~/.themis/skills/)    — lawyer-editable without touching code
#   User skills with the same `name` as a bundled skill win (override).
#
# WHY three skill source formats (all produce the same dict shape):
#   1. Flat .md file   — original format; single file with YAML frontmatter
#   2. Skill directory — <name>/manifest.yaml + SKILL.md + references/*.md +
#                        learnings.md; human-editable source format
#   3. .skill ZIP      — packaged distribution format; built from a skill
#                        directory via build_skill.py; same internal layout as
#                        the directory format but portable as one file

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import NamedTuple, Optional

import litellm
import yaml

_logger = logging.getLogger(__name__)

# WHY: User-writable skills (~/.themis/skills/) are injected verbatim into the
# system prompt. A compromised skill file (via sync tool, rogue editor plugin,
# etc.) could override agent instructions. Bundled skills are trusted (in git);
# only user skills are checked at load time.
_INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?)|"
    r"you\s+are\s+now\s+a|"
    r"disregard\s+your|"
    r"new\s+persona|"
    r"override\s+(all\s+)?instructions?|"
    r"forget\s+(all\s+)?previous)",
    re.IGNORECASE,
)


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
            if _INJECTION_RE.search(skill["body"]):
                _logger.warning(
                    "User skill '%s' contains suspicious override pattern — skipped.",
                    skill["name"],
                )
                continue
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
            # WHY: validate user skills before they can override bundled ones.
            # Bundled skills are version-controlled and trusted; user skills are not.
            if _INJECTION_RE.search(skill["body"]):
                _logger.warning(
                    "User skill '%s' contains suspicious override pattern — skipped.",
                    skill["name"],
                )
                continue
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


def load_skill_stack(
    matter_type: str,
    bundled_skills_dir,
    user_skills_dir,
    agent_skill_names: list[str] | None = None,
    token_cap: int = 12000,
) -> str:
    """Primary skill for matter_type + secondary skills from agent persona. Hard cap on total chars."""
    bundled = Path(bundled_skills_dir)
    user = Path(str(user_skills_dir)).expanduser()
    blocks, loaded = [], set()

    primary = load_skill(matter_type, bundled, user)
    if primary:
        blocks.append(f"## Primary Skill\n{primary}")
        loaded.add(hash(primary))

    for name in (agent_skill_names or []):
        content = _load_by_name(name, bundled, user)
        if content and hash(content) not in loaded:
            blocks.append(f"## Supporting Skill — {name}\n{content}")
            loaded.add(hash(content))

    return "\n\n---\n\n".join(blocks)[:token_cap]


def build_skills_manifest(
    bundled_skills_dir: str | Path,
    user_skills_dir: str | Path,
) -> dict[str, str]:
    """
    Return {name: description} for every skill on disk.
    User skills with the same name override bundled.
    Used by route_skills() to build the LLM routing prompt.
    """
    bundled = _skills_from_dir(Path(bundled_skills_dir))
    user = _skills_from_dir(Path(str(user_skills_dir)).expanduser())

    by_name: dict[str, str] = {}
    for skill in bundled:
        if skill["name"]:
            by_name[skill["name"]] = skill["description"]
    for skill in user:
        if skill["name"]:
            by_name[skill["name"]] = skill["description"]
    return by_name


def _string_match_skill_name(
    matter_type: str,
    bundled_skills_dir: str | Path,
    user_skills_dir: str | Path,
) -> Optional[str]:
    """
    Run keyword/matter_type matching and return the skill NAME (not body).
    Returns None if no match.
    Used as one of the three consensus sources in skill_router.py.
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
            return skill["name"]

    for skill in skills:
        for kw in skill["trigger_keywords"]:
            if kw.lower() in matter_type.lower():
                return skill["name"]

    return None


async def route_skills(
    matter_summary: str,
    manifest: dict[str, str],
    config,
) -> dict:
    """
    Single LiteLLM call to the router model to select relevant skills.

    Returns {"selected": [name, ...], "unmatched": [name, ...]} where:
      selected  — skill names that exist in manifest AND were chosen
      unmatched — names the LLM requested but are not in manifest

    Never raises — returns {"selected": [], "unmatched": []} on any exception.
    """
    if not manifest:
        return {"selected": [], "unmatched": []}

    manifest_lines = "\n".join(
        f"  {name}: {desc}" for name, desc in manifest.items()
    )
    system_prompt = (
        "You are a legal document routing agent. "
        "Given a matter summary and a list of available skills, "
        "select the skills that are most relevant for drafting. "
        "You may select multiple skills. "
        "Return ONLY valid JSON with keys 'selected' (list of skill names to use) "
        "and 'unmatched' (list of skill names you wanted but are not available). "
        "Only include names from the provided list in 'selected'."
    )
    user_message = (
        f"Available skills:\n{manifest_lines}\n\n"
        f"Matter summary: {matter_summary[:500]}\n\n"
        "Return JSON only."
    )

    try:
        response = await litellm.acompletion(
            model=config.skill_router_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        llm_selected: list[str] = data.get("selected") or []
        llm_unmatched: list[str] = data.get("unmatched") or []

        # Filter: only keep names that actually exist in manifest
        valid_selected = [n for n in llm_selected if n in manifest]
        # Names in selected but not in manifest are also unmatched
        spurious = [n for n in llm_selected if n not in manifest]
        all_unmatched = list(dict.fromkeys(llm_unmatched + spurious))

        return {"selected": valid_selected, "unmatched": all_unmatched}

    except Exception:
        return {"selected": [], "unmatched": []}


def _load_by_name(skill_name: str, bundled: Path, user: Path) -> str | None:
    by_name = {}
    for s in [*_skills_from_dir(bundled), *_skills_from_dir(user)]:
        if s["name"]:
            by_name[s["name"]] = s
    skill = by_name.get(skill_name)
    return skill["body"] if skill else None


def _skills_from_dir(directory: Path) -> list[dict]:
    """
    Return parsed skill dicts from every skill source found in directory.

    Three source formats are recognised (processed in order; all produce the
    same dict shape so the rest of the loader is unaware of the difference):
      1. *.md files          — flat single-file skills with YAML frontmatter
      2. *.skill ZIP files   — packaged skills built by build_skill.py
      3. sub-directories     — un-packaged source form (must have manifest.yaml)
    """
    if not directory.exists() or not directory.is_dir():
        return []
    skills = []
    for md_file in directory.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        skills.append(_parse_frontmatter(content))
    for skill_file in directory.glob("*.skill"):
        parsed = _parse_skill_package(skill_file)
        if parsed:
            skills.append(parsed)
    for subdir in directory.iterdir():
        if subdir.is_dir() and (subdir / "manifest.yaml").exists():
            parsed = _parse_skill_directory(subdir)
            if parsed:
                skills.append(parsed)
    return skills


def _parse_skill_package(path: Path) -> dict | None:
    """
    Read a .skill ZIP archive and return a skill dict.

    Expected ZIP layout:
      manifest.yaml       — YAML with name, description, trigger_keywords,
                            matter_types, min_inference_tier
      SKILL.md            — main instruction body
      references/*.md     — appended to body under a ## References section
      learnings.md        — appended as a ## Standing Rules section

    WHY references are concatenated into body:
      The rest of the loader only passes body to the LLM prompt. Concatenating
      here keeps all downstream code unchanged while giving the LLM full
      context from reference files.
    """
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()

            raw_manifest = zf.read("manifest.yaml").decode("utf-8")
            meta = yaml.safe_load(raw_manifest) or {}

            skill_md = zf.read("SKILL.md").decode("utf-8") if "SKILL.md" in names else ""
            body_parts = [skill_md.strip()]

            ref_files = sorted(n for n in names if n.startswith("references/") and n.endswith(".md"))
            if ref_files:
                body_parts.append("## References")
                for ref in ref_files:
                    ref_content = zf.read(ref).decode("utf-8").strip()
                    ref_name = Path(ref).stem.replace("-", " ").replace("_", " ").title()
                    body_parts.append(f"### {ref_name}\n{ref_content}")

            if "learnings.md" in names:
                learnings = zf.read("learnings.md").decode("utf-8").strip()
                body_parts.append(f"## Standing Rules\n{learnings}")

        return {
            "name": str(meta.get("name", path.stem)),
            "description": str(meta.get("description", "")),
            "trigger_keywords": _as_list(meta.get("trigger_keywords", [])),
            "matter_types": _as_list(meta.get("matter_types", [])),
            "body": "\n\n".join(body_parts),
            "min_tier": int(meta.get("min_inference_tier", 4)),
        }
    except Exception:
        return None


def _parse_skill_directory(path: Path) -> dict | None:
    """
    Read a skill source directory and return a skill dict.

    Expected layout:
      manifest.yaml
      SKILL.md
      references/*.md   (optional)
      learnings.md      (optional)

    WHY support directory form in addition to .skill ZIPs:
      During development, lawyers and developers edit skill files directly.
      Requiring a build step before testing would slow iteration. The loader
      reads directories at runtime; build_skill.py is only needed for
      distribution.
    """
    try:
        raw_manifest = (path / "manifest.yaml").read_text(encoding="utf-8")
        meta = yaml.safe_load(raw_manifest) or {}

        skill_md_path = path / "SKILL.md"
        skill_md = skill_md_path.read_text(encoding="utf-8").strip() if skill_md_path.exists() else ""
        body_parts = [skill_md]

        refs_dir = path / "references"
        if refs_dir.is_dir():
            ref_files = sorted(refs_dir.glob("*.md"))
            if ref_files:
                body_parts.append("## References")
                for ref in ref_files:
                    ref_content = ref.read_text(encoding="utf-8").strip()
                    ref_name = ref.stem.replace("-", " ").replace("_", " ").title()
                    body_parts.append(f"### {ref_name}\n{ref_content}")

        learnings_path = path / "learnings.md"
        if learnings_path.exists():
            learnings = learnings_path.read_text(encoding="utf-8").strip()
            body_parts.append(f"## Standing Rules\n{learnings}")

        return {
            "name": str(meta.get("name", path.name)),
            "description": str(meta.get("description", "")),
            "trigger_keywords": _as_list(meta.get("trigger_keywords", [])),
            "matter_types": _as_list(meta.get("matter_types", [])),
            "body": "\n\n".join(part for part in body_parts if part),
            "min_tier": int(meta.get("min_inference_tier", 4)),
        }
    except Exception:
        return None


def _parse_frontmatter(content: str) -> dict:
    """
    Parse YAML frontmatter from a skill .md file.

    Returns a dict with: name, description, trigger_keywords, matter_types, body, min_tier.
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
        "description": str(meta.get("description", "")),
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
