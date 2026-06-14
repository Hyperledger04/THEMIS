# Agent registry — create, load, list, and delete custom agent personas.
#
# WHY two directories:
#   Bundled (themis/agents/defaults/)  — ships with the package
#   User (~/.themis/agents/)           — lawyer-created agents
#   User agents with the same `id` as a bundled agent override the bundled one.
#
# Agent YAML format:
#   id:          Short handle used in @mention (e.g. vikram)
#   name:        Display name shown in UI
#   full_name:   Full formal name (shown in document headers if set)
#   persona:     Behaviour description injected into the system prompt
#   face:        Key into faces.py (e.g. sharp_counsel)
#   skills:      List of skill names to auto-load (matches skill file names)
#   tone:        Drafting tone override (e.g. "Aggressive formal")
#   tagline:     One-liner shown in agent selection UI
#   created_at:  ISO date

from __future__ import annotations

import importlib.resources
from datetime import date
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_agent(
    agent_id: str,
    user_agents_dir: str | Path = "~/.themis/agents",
) -> Optional[dict]:
    """
    Load an agent config by ID.
    User agents override bundled agents with the same ID.
    Returns None if not found.
    """
    bundled = _bundled_agents()
    user = _agents_from_dir(Path(str(user_agents_dir)).expanduser())

    # Merge: user wins on ID clash
    by_id: dict[str, dict] = {}
    for a in bundled:
        by_id[a["id"]] = a
    for a in user:
        by_id[a["id"]] = a

    return by_id.get(agent_id.lower())


def list_agents(
    user_agents_dir: str | Path = "~/.themis/agents",
) -> list[dict]:
    """
    Return all available agents (bundled + user), user overrides bundled on ID clash.
    Sorted: user agents first, then bundled, each alphabetically.
    """
    bundled = _bundled_agents()
    user = _agents_from_dir(Path(str(user_agents_dir)).expanduser())

    by_id: dict[str, dict] = {}
    for a in bundled:
        a["source"] = "bundled"
        by_id[a["id"]] = a
    for a in user:
        a["source"] = "custom"
        by_id[a["id"]] = a

    agents = list(by_id.values())
    agents.sort(key=lambda a: (0 if a["source"] == "custom" else 1, a["id"]))
    return agents


def create_agent(agent_data: dict, user_agents_dir: str | Path = "~/.themis/agents") -> Path:
    """
    Save a new agent to the user agents directory.
    Returns the path where it was saved.
    """
    agents_dir = Path(str(user_agents_dir)).expanduser()
    agents_dir.mkdir(parents=True, exist_ok=True)

    agent_id = agent_data["id"].lower().replace(" ", "_")
    agent_data["id"] = agent_id
    if "created_at" not in agent_data:
        agent_data["created_at"] = str(date.today())

    path = agents_dir / f"{agent_id}.yaml"
    path.write_text(yaml.dump(agent_data, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    return path


def delete_agent(agent_id: str, user_agents_dir: str | Path = "~/.themis/agents") -> bool:
    """Delete a user-created agent. Returns True if deleted, False if not found."""
    agents_dir = Path(str(user_agents_dir)).expanduser()
    path = agents_dir / f"{agent_id.lower()}.yaml"
    if path.exists():
        path.unlink()
        return True
    return False


def parse_agent_mention(text: str) -> tuple[Optional[str], str]:
    """
    If text starts with @handle, extract the agent handle and return (handle, rest_of_text).
    If no @mention, returns (None, original_text).

    Examples:
        "@vikram draft an injunction"  → ("vikram", "draft an injunction")
        "I need an injunction"         → (None, "I need an injunction")
    """
    text = text.strip()
    if not text.startswith("@"):
        return None, text
    parts = text.split(None, 1)
    handle = parts[0][1:].lower()  # strip @
    rest = parts[1].strip() if len(parts) > 1 else ""
    return handle, rest


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _bundled_agents() -> list[dict]:
    """Load all agent YAMLs from the package's agents/defaults/ directory."""
    defaults_dir = Path(__file__).parent / "defaults"
    return _agents_from_dir(defaults_dir)


def _agents_from_dir(directory: Path) -> list[dict]:
    if not directory.exists() or not directory.is_dir():
        return []
    agents = []
    for yaml_file in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            # Ensure required fields exist
            data.setdefault("id", yaml_file.stem)
            data.setdefault("name", data["id"].capitalize())
            data.setdefault("persona", "")
            data.setdefault("face", "sharp_counsel")
            data.setdefault("skills", [])
            data.setdefault("tone", "Senior formal")
            data.setdefault("tagline", "")
            agents.append(data)
        except Exception:
            pass
    return agents
