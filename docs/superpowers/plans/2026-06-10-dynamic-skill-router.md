# Dynamic Skill Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert a `skill_router` node between `intake` and `draft` that uses an LLM + string-match + forced-skill union to select the best skill stack for any matter type, with gap logging, a terminal nudge, and CLI/Telegram slash commands.

**Architecture:** A new `SkillRouterNode` is added to `build_graph()` between `intake` and `draft`. It runs three skill-selection sources in parallel (LiteLLM router call, Python string-match, forced names from CLI/Telegram), unions them, loads the stacked skill body into `state["active_skill"]`, and logs any unmatched names to `~/.lexagent/missing_skills.log`. The `draft` node reads `state["active_skill"]` unchanged.

**Tech Stack:** Python 3.11+, LangGraph ≥0.2, LiteLLM (already in pyproject), PyYAML (already in pyproject), rich (already in pyproject), python-telegram-bot (already in pyproject), Typer (already in pyproject).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `lexagent/skills/*.md` (9 files) | Modify | Add `description` field to YAML frontmatter |
| `lexagent/config.py` | Modify | Add `skill_router_model` field |
| `lexagent/state.py` | Modify | Add `forced_skill_names`, `selected_skill_names` |
| `lexagent/skills/loader.py` | Modify | Add `build_skills_manifest()`, `route_skills()`, `_string_match_skill_name()`, update `_parse_frontmatter()` |
| `lexagent/nodes/skill_router.py` | **Create** | Router node — union sources, nudge, gap log |
| `lexagent/graph.py` | Modify | Insert `skill_router` node + update `route_after_intake` edges |
| `lexagent/cli.py` | Modify | Add `skill` command group + `--skill` flag on `draft` |
| `lexagent/gateway/telegram.py` | Modify | Dynamic command registration at startup + `/skill` handler |
| `tests/test_skill_router.py` | **Create** | Unit + integration tests |

---

## Task 1: Add `description` to all skill frontmatter

**Files:**
- Modify: `lexagent/skills/s138_complaint.md`
- Modify: `lexagent/skills/bail_application.md`
- Modify: `lexagent/skills/writ_petition.md`
- Modify: `lexagent/skills/written_statement.md`
- Modify: `lexagent/skills/civil_litigation.md`
- Modify: `lexagent/skills/legal_notice.md`
- Modify: `lexagent/skills/legal_contract.md`
- Modify: `lexagent/skills/filing_checklist.md`
- Modify: `lexagent/skills/starter_argument_pattern.md`
- Modify: `lexagent/skills/starter_drafting_style.md`
- Modify: `lexagent/skills/starter_plain_english_summary.md`

- [ ] **Step 1: Add description line to each skill's YAML frontmatter**

For each file, insert `description: "..."` as the SECOND line (after `name:`). Here are the exact descriptions:

`s138_complaint.md` — after `name: s138_complaint`:
```yaml
description: Criminal complaint for cheque dishonour under S.138 NI Act — S.141 liability, exhibit registry, affidavit.
```

`bail_application.md` — after `name: bail_application`:
```yaml
description: Bail application (regular, anticipatory, default) — grounds ordering, parity argument, S.167(2) right.
```

`writ_petition.md` — after `name: writ_petition`:
```yaml
description: Writ petition under Art.226/32 — synopsis, list of dates, HC/SC mandatory sections, interim relief test.
```

`written_statement.md` — after `name: written_statement`:
```yaml
description: Written statement / civil defence — preliminary objections first, para-by-para tracking, counterclaim.
```

`civil_litigation.md` — after `name: civil_litigation`:
```yaml
description: Civil plaint, injunction application, or general civil suit — CPC structure, valuation, court fee.
```

`legal_notice.md` — after `name: legal_notice`:
```yaml
description: Legal notice under CPC or contract — demand details, statutory deadline, cause of action facts.
```

`legal_contract.md` — after `name: legal_contract`:
```yaml
description: Contract drafting or review — clauses, indemnities, representations, governing law, dispute resolution.
```

`filing_checklist.md` — after `name: filing_checklist`:
```yaml
description: Pre-filing checklist — court fee, process fee, vakalatnama, index of documents verification.
```

`starter_argument_pattern.md` — after `name: starter_argument_pattern`:
```yaml
description: Supporting skill — structured legal argument patterns (IRAC, proposition-authority-application).
```

`starter_drafting_style.md` — after `name: starter_drafting_style`:
```yaml
description: Supporting skill — formal Indian court drafting style, sentence structure, citation formatting.
```

`starter_plain_english_summary.md` — after `name: starter_plain_english_summary`:
```yaml
description: Supporting skill — plain English summary for client communication after court filing.
```

- [ ] **Step 2: Verify frontmatter parses correctly**

```bash
cd /Users/anshoosareen/Lexagent
python -c "
from lexagent.skills.loader import _parse_frontmatter
from pathlib import Path
for f in Path('lexagent/skills').glob('*.md'):
    p = _parse_frontmatter(f.read_text())
    print(f.name, '→', repr(p.get('description', 'MISSING')))
"
```
Expected: each file prints a non-empty description string (not `'MISSING'`).

- [ ] **Step 3: Commit**

```bash
git add lexagent/skills/*.md
git commit -m "feat(skills): add description field to all skill frontmatter"
```

---

## Task 2: Update `_parse_frontmatter()` and add `build_skills_manifest()` + `route_skills()` + `_string_match_skill_name()`

**Files:**
- Modify: `lexagent/skills/loader.py`
- Test: `tests/test_skill_router.py`

- [ ] **Step 1: Write failing tests for the new loader functions**

Create `tests/test_skill_router.py`:

```python
"""Tests for the dynamic skill router — manifest, LLM router call, string-match."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from lexagent.skills.loader import (
    _parse_frontmatter,
    _string_match_skill_name,
    build_skills_manifest,
    route_skills,
)


# ── _parse_frontmatter extracts description ──────────────────────────────────

def test_parse_frontmatter_extracts_description():
    content = (
        "---\n"
        "name: test_skill\n"
        "description: A test skill for unit testing.\n"
        "trigger_keywords: [test, demo]\n"
        "matter_types: [test]\n"
        "---\n\n# Body\n"
    )
    parsed = _parse_frontmatter(content)
    assert parsed["description"] == "A test skill for unit testing."


def test_parse_frontmatter_description_defaults_to_empty():
    content = (
        "---\n"
        "name: no_desc\n"
        "trigger_keywords: [x]\n"
        "matter_types: [x]\n"
        "---\n\n# Body\n"
    )
    parsed = _parse_frontmatter(content)
    assert parsed["description"] == ""


# ── build_skills_manifest ─────────────────────────────────────────────────────

def test_build_skills_manifest_returns_name_description_dict(tmp_path):
    skill_a = tmp_path / "skill_a.md"
    skill_a.write_text(
        "---\nname: skill_a\ndescription: Desc A.\ntrigger_keywords: [a]\nmatter_types: [a]\n---\n\n# Body A\n"
    )
    skill_b = tmp_path / "skill_b.md"
    skill_b.write_text(
        "---\nname: skill_b\ndescription: Desc B.\ntrigger_keywords: [b]\nmatter_types: [b]\n---\n\n# Body B\n"
    )
    empty_user = tmp_path / "user_skills"
    empty_user.mkdir()

    manifest = build_skills_manifest(tmp_path, empty_user)
    assert manifest == {"skill_a": "Desc A.", "skill_b": "Desc B."}


def test_build_skills_manifest_user_overrides_bundled(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    user = tmp_path / "user"
    user.mkdir()

    (bundled / "s138.md").write_text(
        "---\nname: s138\ndescription: Bundled desc.\ntrigger_keywords: [x]\nmatter_types: [x]\n---\n"
    )
    (user / "s138.md").write_text(
        "---\nname: s138\ndescription: User override desc.\ntrigger_keywords: [x]\nmatter_types: [x]\n---\n"
    )
    manifest = build_skills_manifest(bundled, user)
    assert manifest["s138"] == "User override desc."


# ── _string_match_skill_name ──────────────────────────────────────────────────

def test_string_match_returns_name_for_s138(tmp_path):
    skill_file = tmp_path / "s138_complaint.md"
    skill_file.write_text(
        "---\nname: s138_complaint\ndescription: S138.\ntrigger_keywords: [cheque, 138, ni act]\nmatter_types: [s138_complaint]\n---\n"
    )
    empty = tmp_path / "user"
    empty.mkdir()

    result = _string_match_skill_name("cheque dishonour case", tmp_path, empty)
    assert result == "s138_complaint"


def test_string_match_returns_none_when_no_match(tmp_path):
    empty = tmp_path / "user"
    empty.mkdir()
    result = _string_match_skill_name("arbitration petition", tmp_path, empty)
    assert result is None


# ── route_skills ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_skills_returns_selected_from_llm():
    manifest = {
        "s138_complaint": "S.138 cheque dishonour.",
        "bail_application": "Bail application.",
    }
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"selected": ["s138_complaint"], "unmatched": []}'
                )
            )
        ]
    )
    cfg = SimpleNamespace(skill_router_model="openai/gpt-4.1-mini", openai_api_key="test")
    with patch("lexagent.skills.loader.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        result = await route_skills("S.138 cheque case", manifest, cfg)
    assert result["selected"] == ["s138_complaint"]
    assert result["unmatched"] == []


@pytest.mark.asyncio
async def test_route_skills_filters_nonexistent_skills():
    manifest = {"s138_complaint": "S.138 cheque."}
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"selected": ["s138_complaint", "arbitration_petition"], "unmatched": ["arbitration_petition"]}'
                )
            )
        ]
    )
    cfg = SimpleNamespace(skill_router_model="openai/gpt-4.1-mini", openai_api_key="test")
    with patch("lexagent.skills.loader.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        result = await route_skills("arbitration matter", manifest, cfg)
    # Only skill that exists in manifest should be in selected
    assert "arbitration_petition" not in result["selected"]


@pytest.mark.asyncio
async def test_route_skills_returns_empty_on_exception():
    manifest = {"s138_complaint": "S.138 cheque."}
    cfg = SimpleNamespace(skill_router_model="openai/gpt-4.1-mini", openai_api_key="test")
    with patch("lexagent.skills.loader.litellm.acompletion", side_effect=Exception("API error")):
        result = await route_skills("any matter", manifest, cfg)
    assert result == {"selected": [], "unmatched": []}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/anshoosareen/Lexagent
pytest tests/test_skill_router.py -v 2>&1 | tail -20
```
Expected: `ImportError` or `AttributeError` — `build_skills_manifest`, `route_skills`, `_string_match_skill_name` not yet defined.

- [ ] **Step 3: Update `_parse_frontmatter()` to extract `description`**

In `lexagent/skills/loader.py`, replace the return dict in `_parse_frontmatter()`:

```python
    return {
        "name": str(meta.get("name", "")),
        "description": str(meta.get("description", "")),
        "trigger_keywords": _as_list(meta.get("trigger_keywords", [])),
        "matter_types": _as_list(meta.get("matter_types", [])),
        "body": body,
        "min_tier": int(meta.get("min_inference_tier", 4)),
    }
```

Also update the no-frontmatter fallback return to include `"description": ""`:

```python
    if not match:
        return {"name": "", "description": "", "trigger_keywords": [], "matter_types": [], "body": content}
```

- [ ] **Step 4: Add `build_skills_manifest()`, `_string_match_skill_name()`, and `route_skills()` to `loader.py`**

Add these imports at the top of `loader.py` (after the existing imports):

```python
import litellm
```

Add these three functions after `_load_by_name()`:

```python
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
    Run the existing keyword/matter_type matching logic but return the skill
    NAME instead of its body. Returns None if no match.
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

    Returns {"selected": [name, ...], "unmatched": [name, ...]}
    where:
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
        # Anything in selected but not in manifest is also unmatched
        spurious = [n for n in llm_selected if n not in manifest]
        all_unmatched = list(dict.fromkeys(llm_unmatched + spurious))

        return {"selected": valid_selected, "unmatched": all_unmatched}

    except Exception:
        return {"selected": [], "unmatched": []}
```

Also add `import json` to the top of `loader.py`.

- [ ] **Step 5: Run the tests**

```bash
cd /Users/anshoosareen/Lexagent
pytest tests/test_skill_router.py -v 2>&1 | tail -30
```
Expected: all tests pass.

- [ ] **Step 6: Run existing loader tests to confirm nothing broke**

```bash
pytest tests/ -k "loader or skill" -v 2>&1 | tail -20
```
Expected: all pre-existing skill/loader tests still pass.

- [ ] **Step 7: Commit**

```bash
git add lexagent/skills/loader.py tests/test_skill_router.py
git commit -m "feat(loader): add description field, build_skills_manifest, route_skills, _string_match_skill_name"
```

---

## Task 3: Add `skill_router_model` to `LexConfig` and new state fields to `LexState`

**Files:**
- Modify: `lexagent/config.py`
- Modify: `lexagent/state.py`

- [ ] **Step 1: Add `skill_router_model` to `LexConfig`**

In `lexagent/config.py`, add this field in the "Agent behaviour" section (after `enable_prompt_caching`):

```python
    # Skill router — uses a cheap fast model for routing decisions (not drafting).
    # Change via LEX_SKILL_ROUTER_MODEL env var. Any LiteLLM-compatible model string.
    skill_router_model: str = Field(
        "openai/gpt-4.1-mini",
        validation_alias=AliasChoices("LEX_SKILL_ROUTER_MODEL", "skill_router_model"),
    )
```

- [ ] **Step 2: Add `forced_skill_names` and `selected_skill_names` to `LexState`**

In `lexagent/state.py`, add these two fields in the `# --- Meta ---` section (after `active_skill`):

```python
    # Dynamic skill router (Phase: dynamic-skill-router)
    # forced_skill_names: set by --skill CLI flag or /skill Telegram command before graph runs.
    # selected_skill_names: names actually loaded by skill_router node (audit/debug).
    forced_skill_names: Optional[List[str]]
    selected_skill_names: Optional[List[str]]
```

- [ ] **Step 3: Verify config and state parse correctly**

```bash
cd /Users/anshoosareen/Lexagent
python -c "
from lexagent.config import LexConfig
cfg = LexConfig()
print('skill_router_model:', cfg.skill_router_model)
from lexagent.state import LexState
print('State keys include forced_skill_names:', 'forced_skill_names' in LexState.__annotations__)
print('State keys include selected_skill_names:', 'selected_skill_names' in LexState.__annotations__)
"
```
Expected output:
```
skill_router_model: openai/gpt-4.1-mini
State keys include forced_skill_names: True
State keys include selected_skill_names: True
```

- [ ] **Step 4: Commit**

```bash
git add lexagent/config.py lexagent/state.py
git commit -m "feat(config,state): add skill_router_model, forced_skill_names, selected_skill_names"
```

---

## Task 4: Create `lexagent/nodes/skill_router.py`

**Files:**
- Create: `lexagent/nodes/skill_router.py`
- Test: `tests/test_skill_router.py` (extend)

- [ ] **Step 1: Write failing tests for the router node**

Append to `tests/test_skill_router.py`:

```python
# ── skill_router node ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_skill_router_node_loads_skill_into_state(tmp_path):
    """Router node should write active_skill and selected_skill_names to state."""
    skill_file = tmp_path / "s138_complaint.md"
    skill_file.write_text(
        "---\n"
        "name: s138_complaint\n"
        "description: S.138 cheque dishonour complaint.\n"
        "trigger_keywords: [cheque, 138, ni act, dishonour]\n"
        "matter_types: [s138_complaint]\n"
        "---\n\n# S138 Skill Body\n"
    )
    user_dir = tmp_path / "user"
    user_dir.mkdir()

    from lexagent.nodes.skill_router import run as router_run

    state = {
        "user_input": "cheque dishonour case against ABC Ltd",
        "matter_type": "s138_complaint",
        "intake_complete": True,
        "forced_skill_names": None,
        "messages": [],
    }

    mock_route_result = {"selected": ["s138_complaint"], "unmatched": []}

    with (
        patch("lexagent.nodes.skill_router.BUNDLED_SKILLS_DIR", tmp_path),
        patch("lexagent.nodes.skill_router.route_skills", new=AsyncMock(return_value=mock_route_result)),
    ):
        result = await router_run(state)

    assert "active_skill" in result
    assert "S138 Skill Body" in result["active_skill"]
    assert result["selected_skill_names"] == ["s138_complaint"]


@pytest.mark.asyncio
async def test_skill_router_node_unions_forced_with_llm(tmp_path):
    """forced_skill_names should be added even if LLM picks nothing."""
    skill_a = tmp_path / "s138_complaint.md"
    skill_a.write_text(
        "---\nname: s138_complaint\ndescription: S138.\ntrigger_keywords: [cheque]\nmatter_types: [s138_complaint]\n---\n\n# S138\n"
    )
    skill_b = tmp_path / "bail_application.md"
    skill_b.write_text(
        "---\nname: bail_application\ndescription: Bail.\ntrigger_keywords: [bail]\nmatter_types: [bail_application]\n---\n\n# Bail\n"
    )
    user_dir = tmp_path / "user"
    user_dir.mkdir()

    from lexagent.nodes.skill_router import run as router_run

    state = {
        "user_input": "cheque dishonour and bail needed",
        "matter_type": "s138_complaint",
        "intake_complete": True,
        "forced_skill_names": ["bail_application"],
        "messages": [],
    }

    mock_route_result = {"selected": ["s138_complaint"], "unmatched": []}

    with (
        patch("lexagent.nodes.skill_router.BUNDLED_SKILLS_DIR", tmp_path),
        patch("lexagent.nodes.skill_router.route_skills", new=AsyncMock(return_value=mock_route_result)),
    ):
        result = await router_run(state)

    assert result["selected_skill_names"] is not None
    assert "bail_application" in result["selected_skill_names"]
    assert "s138_complaint" in result["selected_skill_names"]


@pytest.mark.asyncio
async def test_skill_router_node_no_error_on_llm_failure(tmp_path):
    """Node must not raise even if LLM call fails — graceful degradation."""
    user_dir = tmp_path / "user"
    user_dir.mkdir()

    from lexagent.nodes.skill_router import run as router_run

    state = {
        "user_input": "some matter",
        "matter_type": "writ_petition",
        "intake_complete": True,
        "forced_skill_names": None,
        "messages": [],
    }

    with (
        patch("lexagent.nodes.skill_router.BUNDLED_SKILLS_DIR", tmp_path),
        patch("lexagent.nodes.skill_router.route_skills", new=AsyncMock(side_effect=Exception("LLM down"))),
    ):
        result = await router_run(state)

    assert "error" not in result or result.get("error") is None
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_skill_router.py::test_skill_router_node_loads_skill_into_state -v 2>&1 | tail -10
```
Expected: `ModuleNotFoundError` — `lexagent.nodes.skill_router` not yet created.

- [ ] **Step 3: Create `lexagent/nodes/skill_router.py`**

```python
# Skill Router Node — inserted between intake and draft.
#
# Runs three skill-selection sources and unions them:
#   1. LLM router (gpt-4.1-mini by default) — semantic understanding
#   2. String-match (existing loader logic) — deterministic fallback
#   3. forced_skill_names (CLI --skill flag or Telegram /skill command) — manual override
#
# Result is loaded into state["active_skill"] via load_skill_stack().
# Gap logging: unmatched skill names are written to ~/.lexagent/missing_skills.log.
# Terminal nudge: shown via rich.Panel to stderr when gaps are detected.

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from lexagent.config import LexConfig
from lexagent.skills.loader import (
    _string_match_skill_name,
    build_skills_manifest,
    load_skill_stack,
    route_skills,
)
from lexagent.state import LexState

# WHY: BUNDLED_SKILLS_DIR is a module-level constant so tests can patch it
# without patching the entire config. Tests set it to a tmp_path with fixture skills.
BUNDLED_SKILLS_DIR = Path(__file__).parent.parent / "skills"

_stderr_console = Console(stderr=True)


async def run(state: LexState) -> dict:
    """
    Select and load the best skill stack for this matter.
    Always succeeds — falls back to empty skill (base prompt only) on any failure.
    """
    try:
        cfg = LexConfig()
        user_skills_dir = Path(cfg.skills_dir).expanduser()

        matter_type = state.get("matter_type") or ""
        user_input = state.get("user_input") or ""
        matter_summary = f"{matter_type} — {user_input}"[:500]
        forced: list[str] = list(state.get("forced_skill_names") or [])

        # ── Source 1: LLM router ───────────────────────────────────────────
        manifest = build_skills_manifest(BUNDLED_SKILLS_DIR, user_skills_dir)
        router_result = await route_skills(matter_summary, manifest, cfg)
        llm_selected: list[str] = router_result.get("selected") or []
        unmatched: list[str] = router_result.get("unmatched") or []

        # ── Source 2: string-match ─────────────────────────────────────────
        string_name = _string_match_skill_name(matter_type, BUNDLED_SKILLS_DIR, user_skills_dir)
        string_matched: list[str] = [string_name] if string_name else []

        # ── Source 3: forced ───────────────────────────────────────────────
        # (already captured above)

        # ── Union (dedup, preserve order: llm first, then string, then forced) ──
        seen: set[str] = set()
        final_names: list[str] = []
        for name in [*llm_selected, *string_matched, *forced]:
            if name and name not in seen:
                seen.add(name)
                final_names.append(name)

        # ── Load skill bodies ──────────────────────────────────────────────
        active_skill = ""
        if final_names:
            # load_skill_stack expects matter_type for primary + agent_skill_names for secondary.
            # WHY: We pass the first name as matter_type (its name matches exactly) and the
            # rest as agent_skill_names. load_skill_stack deduplicates by content hash.
            active_skill = load_skill_stack(
                final_names[0],
                BUNDLED_SKILLS_DIR,
                user_skills_dir,
                agent_skill_names=final_names[1:],
            )

        # ── Gap log + terminal nudge ───────────────────────────────────────
        if unmatched:
            _append_gap_log(matter_summary, unmatched, cfg)
            _show_gap_nudge(unmatched)

        # ── Routing summary line ───────────────────────────────────────────
        if final_names:
            display = ", ".join(final_names)
            _stderr_console.print(f"[dim]Skill router:[/dim] {display}")
        else:
            _stderr_console.print("[dim]Skill router: no skill loaded — using base prompt[/dim]")

        active_skill_name = ", ".join(final_names) if final_names else None

        return {
            "active_skill": active_skill or None,
            "active_skill_name": active_skill_name,
            "selected_skill_names": final_names if final_names else None,
        }

    except Exception as e:
        # WHY: Never block the graph — degrade silently to base prompt.
        _stderr_console.print(f"[dim yellow]Skill router failed ({e}); using base prompt.[/dim yellow]")
        return {}


def _append_gap_log(matter_summary: str, missing: list[str], cfg: LexConfig) -> None:
    """Append one line per gap event to ~/.lexagent/missing_skills.log."""
    try:
        log_path = Path(cfg.home_dir).expanduser() / "missing_skills.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        safe_summary = matter_summary.replace('"', "'")[:120]
        missing_json = str(missing).replace("'", '"')
        line = f'{ts}  matter="{safe_summary}"  missing={missing_json}\n'
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # gap log failure must never surface to the user


def _show_gap_nudge(missing: list[str]) -> None:
    """Show a Rich panel nudge to stderr listing unmatched skills."""
    missing_lines = "\n".join(f"    {name}  — not found" for name in missing)
    create_cmd = f"lex skill create {missing[0]}" if missing else "lex skill create <name>"
    panel_text = (
        f"The router identified {len(missing)} skill(s) not yet in your library:\n\n"
        f"{missing_lines}\n\n"
        "Drafting without it. To add this skill later:\n"
        f"  [bold cyan]{create_cmd}[/bold cyan]\n"
        "Or load an existing skill manually:\n"
        "  [bold cyan]lex skill load <name>[/bold cyan]   /   Telegram: [bold cyan]/skill <name>[/bold cyan]"
    )
    _stderr_console.print(
        Panel(panel_text, title="[yellow]Skill Gap Detected[/yellow]", border_style="yellow"),
        file=sys.stderr,
    )
```

- [ ] **Step 4: Run the router node tests**

```bash
pytest tests/test_skill_router.py -v 2>&1 | tail -30
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add lexagent/nodes/skill_router.py tests/test_skill_router.py
git commit -m "feat(skill-router): new router node — LLM+string-match+forced union, gap log, terminal nudge"
```

---

## Task 5: Wire `skill_router` into `graph.py`

**Files:**
- Modify: `lexagent/graph.py`

- [ ] **Step 1: Add the `skill_router` import and node to `build_graph()`**

In `lexagent/graph.py`, add to the import line at the top:

```python
from lexagent.nodes import cite, draft, intake, react_research, retrieve, review, skill_router
```

- [ ] **Step 2: Update `route_after_intake` in `_make_routes()` to route to `skill_router` instead of `research`/`retrieve`**

Replace the routing block inside `route_after_intake`:

```python
        if state.get("intake_complete"):
            if state.get("workflow_mode") == "contract_review":
                return "contract_review"
            # WHY: skill_router runs before research/retrieve/draft so the skill
            # body is already in state["active_skill"] by the time draft reads it.
            return "skill_router"
        return END
```

- [ ] **Step 3: Add a new `route_after_skill_router` routing function inside `_make_routes()`**

Add this function after `route_after_intake` and before `route_after_research`:

```python
    def route_after_skill_router(state: LexState) -> str:
        """
        After skill_router runs, proceed to research or retrieve as before.
        skill_router itself never errors out — but honour any upstream error.
        """
        if state.get("error"):
            return END
        mt = (state.get("matter_type") or "").lower()
        if any(t in mt for t in _NO_RESEARCH_TYPES):
            return "retrieve"
        return "research"
```

Add it to the return tuple at the end of `_make_routes()`:

```python
    return route_after_intake, route_after_skill_router, route_after_research, route_after_draft
```

- [ ] **Step 4: Update `build_graph()` to register the node and new edges**

In `build_graph()`, update the destructuring:

```python
    route_after_intake, route_after_skill_router, route_after_research, route_after_draft = _make_routes(cfg)
```

Add the node registration (after the other `add_node` calls):

```python
    graph.add_node("skill_router", skill_router.run)
```

Replace:
```python
    graph.add_conditional_edges("intake", route_after_intake)
```
With:
```python
    graph.add_conditional_edges("intake", route_after_intake)
    graph.add_conditional_edges("skill_router", route_after_skill_router)
```

- [ ] **Step 5: Verify graph compiles without error**

```bash
cd /Users/anshoosareen/Lexagent
python -c "
from lexagent.graph import build_graph
g = build_graph()
print('Graph nodes:', list(g.nodes))
"
```
Expected output includes `skill_router` in the node list.

- [ ] **Step 6: Run the full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -40
```
Expected: all existing tests pass, new router tests pass.

- [ ] **Step 7: Commit**

```bash
git add lexagent/graph.py
git commit -m "feat(graph): insert skill_router node between intake and draft"
```

---

## Task 6: Add `lex skill` command group and `--skill` flag to CLI

**Files:**
- Modify: `lexagent/cli.py`

- [ ] **Step 1: Add the `--skill` flag to the `draft` command**

In `lexagent/cli.py`, add to the `draft()` function signature after the `agent` parameter:

```python
    skill: Optional[List[str]] = typer.Option(
        None,
        "--skill",
        "-s",
        help="Force-load a skill by name (repeatable: --skill s138_complaint --skill bail_application)",
    ),
```

Also add `from typing import List` to imports if not already present (it's in `Optional` imports).

- [ ] **Step 2: Wire `--skill` into the initial state before graph invocation**

Inside the `draft()` function, find where the initial state dict is built (look for `"user_input": brief`). Add `forced_skill_names` to that dict:

```python
        "forced_skill_names": list(skill) if skill else None,
```

- [ ] **Step 3: Create the `skill` Typer command group**

Add this block after the `agent_app` definition (around line 65 in the current file):

```python
skill_app = typer.Typer(name="skill", help="List, inspect, and create skills.")
app.add_typer(skill_app, name="skill")


@skill_app.command("list")
def skill_list() -> None:
    """List all available skills with name, description, and source (bundled/user)."""
    from lexagent.config import LexConfig
    from lexagent.skills.loader import _skills_from_dir
    from pathlib import Path
    from rich.table import Table

    cfg = LexConfig()
    bundled_dir = Path(__file__).parent / "skills"
    user_dir = Path(cfg.skills_dir).expanduser()

    bundled_names: set[str] = set()
    rows: list[tuple[str, str, str]] = []

    for skill in _skills_from_dir(bundled_dir):
        if skill["name"]:
            bundled_names.add(skill["name"])
            rows.append((skill["name"], skill["description"], "bundled"))

    for skill in _skills_from_dir(user_dir):
        if skill["name"]:
            source = "user (overrides bundled)" if skill["name"] in bundled_names else "user"
            # Replace bundled row with user row
            rows = [(n, d, s) for n, d, s in rows if n != skill["name"]]
            rows.append((skill["name"], skill["description"], source))

    rows.sort(key=lambda r: r[0])

    table = Table(title="Available Skills", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Source", style="dim")
    for name, desc, source in rows:
        table.add_row(name, desc or "[dim]no description[/dim]", source)

    console.print(table)


@skill_app.command("load")
def skill_load(name: str = typer.Argument(..., help="Skill name to print (e.g. s138_complaint)")) -> None:
    """Print the full body of a named skill to the terminal."""
    from lexagent.config import LexConfig
    from lexagent.skills.loader import _load_by_name
    from pathlib import Path

    cfg = LexConfig()
    bundled_dir = Path(__file__).parent / "skills"
    user_dir = Path(cfg.skills_dir).expanduser()

    body = _load_by_name(name, bundled_dir, user_dir)
    if not body:
        console.print(f"[red]Skill '{name}' not found.[/red] Run [bold cyan]lex skill list[/bold cyan] to see available skills.")
        raise typer.Exit(1)
    console.print(body)


@skill_app.command("create")
def skill_create(name: str = typer.Argument(..., help="New skill name (e.g. arbitration_petition)")) -> None:
    """Scaffold a new skill .md file in ~/.lexagent/skills/ and open in $EDITOR."""
    import os
    from lexagent.config import LexConfig
    from pathlib import Path

    cfg = LexConfig()
    skills_dir = Path(cfg.skills_dir).expanduser()
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill_path = skills_dir / f"{name}.md"
    if skill_path.exists():
        console.print(f"[yellow]Skill '{name}' already exists at {skill_path}[/yellow]")
        raise typer.Exit(0)

    template = (
        f"---\n"
        f"name: {name}\n"
        f"description: TODO — one sentence describing when to use this skill.\n"
        f"trigger_keywords: [keyword1, keyword2]\n"
        f"matter_types: [{name}]\n"
        f"---\n\n"
        f"# {name.replace('_', ' ').title()} Skill\n\n"
        f"## Governing Law\n\n## Party Labels\n\n## Required Sections\n\n## Common Errors to Avoid\n"
    )
    skill_path.write_text(template, encoding="utf-8")
    console.print(f"[green]✓ Created:[/green] {skill_path}")

    editor = os.environ.get("EDITOR")
    if editor:
        os.execlp(editor, editor, str(skill_path))
```

- [ ] **Step 4: Verify CLI commands work**

```bash
cd /Users/anshoosareen/Lexagent
python -m lexagent.cli skill list 2>&1 | head -20
python -m lexagent.cli skill --help
```
Expected: table of skills printed, help shows `list`, `load`, `create` subcommands.

- [ ] **Step 5: Run tests**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add lexagent/cli.py
git commit -m "feat(cli): add lex skill list/load/create commands and --skill flag on draft"
```

---

## Task 7: Dynamic Telegram slash command registration + `/skill` handler

**Files:**
- Modify: `lexagent/gateway/telegram.py`

- [ ] **Step 1: Read the current bot startup section**

Find where `Application.builder().token(token).build()` is called (around line 1252). The startup sequence is what we'll extend.

- [ ] **Step 2: Add `_register_skill_commands()` helper function**

Add this function before the main `telegram` CLI command function (near where the Application is built):

```python
async def _register_skill_commands(app_instance) -> None:
    """
    Register dynamic slash commands from the skills manifest at bot startup.
    Adding a new .md skill file automatically makes its command available — no code change needed.
    WHY: python-telegram-bot's set_my_commands() replaces the full command list atomically.
    """
    from pathlib import Path
    from telegram import BotCommand
    from lexagent.config import LexConfig
    from lexagent.skills.loader import build_skills_manifest

    cfg = LexConfig()
    bundled_dir = Path(__file__).parent.parent / "skills"
    user_dir = Path(cfg.skills_dir).expanduser()
    manifest = build_skills_manifest(bundled_dir, user_dir)

    # Base commands always present
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help"),
        BotCommand("draft", "Draft a legal document"),
        BotCommand("skill_list", "List available skills"),
        BotCommand("skill", "Load a skill by name: /skill <name>"),
    ]

    # Dynamic per-skill shorthand commands
    for name, desc in manifest.items():
        # Telegram command names: max 32 chars, lowercase, underscores only
        cmd_name = name[:32].lower()
        short_desc = desc[:256] if desc else f"Load {name} skill"
        commands.append(BotCommand(cmd_name, short_desc))

    try:
        await app_instance.bot.set_my_commands(commands)
    except Exception as e:
        # Non-fatal — commands just won't show in the menu
        import logging
        logging.getLogger(__name__).warning("Failed to register Telegram commands: %s", e)
```

- [ ] **Step 3: Add `/skill` and `/skill_list` message handlers**

Find the section where message handlers are added to the Application (look for `app.add_handler`). Add these handlers:

```python
    from telegram.ext import CommandHandler

    async def handle_skill_list(update, context):
        """Reply with a formatted list of all available skills."""
        from pathlib import Path
        from lexagent.config import LexConfig
        from lexagent.skills.loader import build_skills_manifest

        cfg = LexConfig()
        bundled_dir = Path(__file__).parent.parent / "skills"
        user_dir = Path(cfg.skills_dir).expanduser()
        manifest = build_skills_manifest(bundled_dir, user_dir)

        if not manifest:
            await update.message.reply_text("No skills available.")
            return

        lines = ["*Available Skills:*\n"]
        for name, desc in sorted(manifest.items()):
            lines.append(f"• `{name}` — {desc or 'no description'}")
        lines.append(f"\nUse `/skill <name>` to force-load a skill on your next draft.")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def handle_skill_load(update, context):
        """
        /skill <name> — store skill name in user_data so the next draft uses it.
        Additive: calling /skill again adds to the forced set.
        """
        args = context.args
        if not args:
            await update.message.reply_text(
                "Usage: `/skill <name>`\nExample: `/skill bail_application`\n\n"
                "Run `/skill_list` to see all available skills.",
                parse_mode="Markdown",
            )
            return

        skill_name = args[0].strip()

        # Validate skill exists
        from pathlib import Path
        from lexagent.config import LexConfig
        from lexagent.skills.loader import build_skills_manifest

        cfg = LexConfig()
        bundled_dir = Path(__file__).parent.parent / "skills"
        user_dir = Path(cfg.skills_dir).expanduser()
        manifest = build_skills_manifest(bundled_dir, user_dir)

        if skill_name not in manifest:
            close = [n for n in manifest if skill_name in n or n in skill_name]
            hint = f"\n\nDid you mean: `{'`, `'.join(close[:3])}`?" if close else ""
            await update.message.reply_text(
                f"Skill `{skill_name}` not found.{hint}\n\nRun `/skill_list` to see all available skills.",
                parse_mode="Markdown",
            )
            return

        # Store in user_data for next draft invocation
        forced: list = context.user_data.get("forced_skill_names", [])
        if skill_name not in forced:
            forced.append(skill_name)
        context.user_data["forced_skill_names"] = forced

        await update.message.reply_text(
            f"✓ Skill `{skill_name}` queued for your next draft.\n"
            f"Current forced skills: `{', '.join(forced)}`\n\n"
            "Send your matter brief to proceed.",
            parse_mode="Markdown",
        )

    app.add_handler(CommandHandler("skill_list", handle_skill_list))
    app.add_handler(CommandHandler("skill", handle_skill_load))
```

- [ ] **Step 4: Wire `forced_skill_names` from `user_data` into the initial state**

Find where `user_input` is placed into the initial LexState dict for the Telegram draft flow (search for `"user_input"` in the telegram handler). Add:

```python
        "forced_skill_names": context.user_data.pop("forced_skill_names", None),
```

This pops it after use so each draft starts fresh (unless the user sends `/skill` again).

- [ ] **Step 5: Call `_register_skill_commands()` at bot startup**

Find where the Application is built and started. Add the async setup call:

```python
    async def post_init(application):
        await _register_skill_commands(application)

    app = Application.builder().token(token).post_init(post_init).build()
```

- [ ] **Step 6: Verify Telegram gateway still starts**

```bash
cd /Users/anshoosareen/Lexagent
python -c "
import importlib
import lexagent.gateway.telegram as tg
print('Telegram gateway imports OK')
"
```
Expected: `Telegram gateway imports OK` with no errors.

- [ ] **Step 7: Run full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add lexagent/gateway/telegram.py
git commit -m "feat(telegram): dynamic skill command registration, /skill and /skill_list handlers"
```

---

## Task 8: Integration test — `--skill` flag to state to router

**Files:**
- Test: `tests/test_skill_router.py` (extend)

- [ ] **Step 1: Add integration test for `--skill` flag propagation**

Append to `tests/test_skill_router.py`:

```python
# ── Integration: --skill flag → forced_skill_names → router ──────────────────

def test_skill_list_command_output(tmp_path, capsys):
    """lex skill list should produce a table with all skill names."""
    from typer.testing import CliRunner
    from lexagent.cli import app
    from pathlib import Path

    runner = CliRunner()
    # Just verify the command doesn't crash and prints something
    result = runner.invoke(app, ["skill", "list"])
    # Exit code 0 even if no skills found (empty table is valid)
    assert result.exit_code == 0


def test_skill_create_creates_file(tmp_path):
    """lex skill create should write a skeleton .md file."""
    import os
    from typer.testing import CliRunner
    from lexagent.cli import app

    runner = CliRunner()
    with runner.isolated_filesystem():
        # patch skills_dir to tmp_path to avoid writing to real ~/.lexagent
        env = {"LEX_SKILLS_DIR": str(tmp_path)}
        result = runner.invoke(app, ["skill", "create", "test_skill_xyz"], env=env)
        assert result.exit_code == 0
        skill_file = tmp_path / "test_skill_xyz.md"
        assert skill_file.exists()
        content = skill_file.read_text()
        assert "name: test_skill_xyz" in content
        assert "description: TODO" in content
```

- [ ] **Step 2: Run all tests**

```bash
cd /Users/anshoosareen/Lexagent
pytest tests/ -v --tb=short 2>&1 | tail -40
```
Expected: full green suite.

- [ ] **Step 3: Final commit**

```bash
git add tests/test_skill_router.py
git commit -m "test(skill-router): integration tests for CLI skill commands"
```

---

## Self-Review

**Spec coverage check:**

| Spec Requirement | Task |
|---|---|
| `description` field in skill frontmatter | Task 1 |
| `_parse_frontmatter()` extracts description | Task 2 |
| `build_skills_manifest()` | Task 2 |
| `route_skills()` LiteLLM call | Task 2 |
| `_string_match_skill_name()` | Task 2 |
| `skill_router_model` in LexConfig | Task 3 |
| `forced_skill_names`, `selected_skill_names` in LexState | Task 3 |
| `skill_router.py` node — union + nudge + gap log | Task 4 |
| `graph.py` — insert node, update edges | Task 5 |
| `lex skill list/load/create` commands | Task 6 |
| `lex draft --skill` flag | Task 6 |
| Telegram dynamic command registration | Task 7 |
| Telegram `/skill` and `/skill_list` handlers | Task 7 |
| `forced_skill_names` from Telegram `user_data` into state | Task 7 |
| Unit tests for all new functions | Tasks 2, 4, 8 |

All spec requirements are covered. No placeholders remain.
