# Contract playbooks: stores a firm's past negotiating positions on key clauses.
#
# WHY YAML files in ~/.themis/playbooks/: same pattern as agents and skills —
# lawyers (or their ops team) can edit them in any text editor, git-track them,
# and share them across a firm without needing a database.
#
# A playbook captures: what clause, what our position is, why, and any precedents.
# During contract review, the active playbook is injected into the system prompt
# so the LLM can flag deviations from firm position automatically.

import uuid
from datetime import date
from pathlib import Path
from typing import Optional

import yaml


_BUNDLED_DIR = Path(__file__).parent / "defaults"
_USER_DIR_DEFAULT = "~/.themis/playbooks"


def _playbooks_dir(user_dir: str = _USER_DIR_DEFAULT) -> Path:
    return Path(user_dir).expanduser()


def list_playbooks(user_dir: str = _USER_DIR_DEFAULT) -> list[dict]:
    """Return all playbooks (bundled + user), sorted by name. User overrides bundled on ID clash."""
    bundled: dict[str, dict] = {}
    if _BUNDLED_DIR.exists():
        for f in _BUNDLED_DIR.glob("*.yaml"):
            pb = _load_file(f)
            if pb:
                pb["source"] = "bundled"
                bundled[pb["id"]] = pb

    user: dict[str, dict] = {}
    ud = _playbooks_dir(user_dir)
    if ud.exists():
        for f in ud.glob("*.yaml"):
            pb = _load_file(f)
            if pb:
                pb["source"] = "custom"
                user[pb["id"]] = pb

    merged = {**bundled, **user}
    return sorted(merged.values(), key=lambda x: x.get("name", x["id"]))


def load_playbook(playbook_id: str, user_dir: str = _USER_DIR_DEFAULT) -> Optional[dict]:
    """Load a single playbook by ID. User copy takes precedence over bundled."""
    ud = _playbooks_dir(user_dir)
    user_file = ud / f"{playbook_id}.yaml"
    if user_file.exists():
        pb = _load_file(user_file)
        if pb:
            pb["source"] = "custom"
            return pb

    bundled_file = _BUNDLED_DIR / f"{playbook_id}.yaml"
    if bundled_file.exists():
        pb = _load_file(bundled_file)
        if pb:
            pb["source"] = "bundled"
            return pb

    return None


def create_playbook(data: dict, user_dir: str = _USER_DIR_DEFAULT) -> Path:
    """Save a new playbook YAML to the user playbooks directory."""
    ud = _playbooks_dir(user_dir)
    ud.mkdir(parents=True, exist_ok=True)
    pb_id = data.get("id") or _slugify(data.get("name", str(uuid.uuid4())[:8]))
    data["id"] = pb_id
    if "created" not in data:
        data["created"] = str(date.today())
    path = ud / f"{pb_id}.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def delete_playbook(playbook_id: str, user_dir: str = _USER_DIR_DEFAULT) -> bool:
    """Delete a user playbook. Returns False if it's bundled or doesn't exist."""
    ud = _playbooks_dir(user_dir)
    target = ud / f"{playbook_id}.yaml"
    if target.exists():
        target.unlink()
        return True
    return False


def load_playbook_spec(playbook_id: str, user_dir: str = _USER_DIR_DEFAULT):
    """
    Load a single playbook as a typed PlaybookSpec.

    WHY separate from load_playbook():
      load_playbook() returns Optional[dict] and three CLI callers depend on that.
      This function returns Optional[PlaybookSpec] for the new PlaybookExecutor.
      Both functions coexist — no existing callers are broken.
    """
    from themis.contract.models import PlaybookSpec
    pb = load_playbook(playbook_id, user_dir)
    if pb is None:
        return None
    return PlaybookSpec.from_dict(pb)


def generate_playbook(contract_text: str, model: str = "anthropic/claude-sonnet-4-6") -> dict:
    """
    Auto-generate a playbook dict from a sample contract via the LLM.
    Returns a raw dict (not PlaybookSpec) so it can be passed to create_playbook().

    WHY sync: Called from the CLI `lex playbook generate` command which runs
    in a threadpool. Avoids adding an async entry point to the CLI.
    """
    import asyncio
    import json as _json

    import litellm

    system = (
        "You are a contract drafting assistant. Analyse the contract and extract "
        "the firm's standard negotiating positions as structured JSON.\n"
        "Return ONLY valid JSON with this schema:\n"
        '{"id": "auto_generated", "name": "string", "contract_type": "string", '
        '"positions": [{"clause": "string", "our_position": "string", "rationale": "string"}], '
        '"notes": "string or null"}'
    )

    async def _call():
        resp = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Contract:\n\n{contract_text[:60_000]}"},
            ],
            response_format={"type": "json_object"},
            request_timeout=60,
        )
        return resp.choices[0].message.content or "{}"

    raw = asyncio.run(_call())
    try:
        return _json.loads(raw)
    except Exception:
        return {"id": "auto_generated", "name": "Generated Playbook", "contract_type": "unknown", "positions": []}


def playbook_to_prompt(pb) -> str:
    """
    Render a playbook as a system prompt block for injection into contract review.

    Accepts both a raw dict (existing CLI callers) and a PlaybookSpec (new executor).
    WHY isinstance branch: PlaybookSpec uses attribute access; dicts use .get().
    """
    from themis.contract.models import PlaybookSpec as _PlaybookSpec
    if isinstance(pb, _PlaybookSpec):
        name = pb.name
        pb_id = pb.id
        contract_type = pb.contract_type
        positions_iter = pb.positions
        notes = pb.notes

        lines = [
            f"## Firm Playbook — {name}",
            f"Contract type: {contract_type}",
            "",
            "### Our Standard Positions",
        ]
        for pos in positions_iter:
            lines.append(f"**{pos.clause}**: {pos.our_position}")
            if pos.rationale:
                lines.append(f"  Rationale: {pos.rationale}")
        if notes:
            lines.append(f"\n### Notes\n{notes}")
        return "\n".join(lines)

    # Original dict path — unchanged for backward compatibility
    lines = [
        f"## Firm Playbook — {pb.get('name', pb['id'])}",
        f"Contract type: {pb.get('contract_type', '—')}",
        "",
        "### Our Standard Positions",
    ]
    for pos in pb.get("positions", []):
        lines.append(f"**{pos.get('clause', '—')}**: {pos.get('our_position', '—')}")
        if pos.get("rationale"):
            lines.append(f"  Rationale: {pos['rationale']}")
    if pb.get("notes"):
        lines.append(f"\n### Notes\n{pb['notes']}")
    return "\n".join(lines)


def _load_file(path: Path) -> Optional[dict]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "id" in data:
            return data
    except Exception:
        pass
    return None


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9_]", "_", text.lower().strip())[:40]
