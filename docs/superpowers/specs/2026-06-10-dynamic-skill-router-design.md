# Dynamic Skill Router — Design Spec

**Date:** 2026-06-10
**Status:** Approved
**Author:** Brainstorming session

---

## Problem

The current skill loader is deterministic Python string matching. It cannot handle:
- Composite matters (S.138 accused also seeking bail → needs two skills)
- Ambiguous briefs (LLM would understand better than a substring check)
- Missing skills (fails silently, no signal to the developer)
- Manual override (lawyer cannot force-load a skill without code change)

---

## Solution Overview

A dedicated `SkillRouterNode` is inserted between `intake` and `draft`. It runs three skill sources in parallel, unions the results, and loads the combined skill stack into `state["active_skill"]`. The draft node is unchanged.

```
intake
  ↓
skill_router (NEW NODE)
  ├─ LLM router (gpt-4.1-mini)          ┐
  ├─ string-match (existing loader)      ├── union → load_skill_stack() → state["active_skill"]
  └─ forced_skill_names (CLI/Telegram)   ┘
  ↓  if gap: Rich panel nudge + missing_skills.log
draft  (unchanged — reads state["active_skill"] as before)
```

---

## Section 1: Architecture

### New graph node

`lexagent/nodes/skill_router.py` — `async def run(state: LexState) -> dict`

Inserted into `graph.py` between `intake` and `draft`:
- Old edge: `intake → draft`
- New edges: `intake → skill_router → draft`
- Condition: runs only when `intake_complete=True` and `workflow_mode != "contract_review"`

### Fallback chain

The router never blocks the graph. Three levels:
1. LLM router call succeeds → use selected skills (+ string-match union + forced)
2. LLM router call fails → string-match covers obvious cases alone
3. Both fail → no skill loaded (existing behaviour — draft uses base prompt only)

Fallback is transparent: a `[dim]` Rich line notes which path was taken.

---

## Section 2: Manifest + Router LLM Call

### `description` field in skill frontmatter

Every skill `.md` file gets a new `description` field (one sentence, ≤ 100 chars):

```yaml
---
name: s138_complaint
description: Criminal complaint for cheque dishonour under S.138 NI Act — S.141 liability, exhibit registry, affidavit.
trigger_keywords: [...]
matter_types: [...]
---
```

`_parse_frontmatter()` in `loader.py` is updated to extract `description`.

### New functions in `loader.py`

**`build_skills_manifest(bundled_dir, user_dir) -> dict[str, str]`**
- Scans both directories, returns `{name: description}` for every skill on disk
- User skills override bundled by name (existing behaviour preserved)
- ~500 tokens for 10 skills

**`route_skills(matter_summary, manifest, config) -> dict`**
- Single LiteLLM call to `config.skill_router_model`
- System prompt: "You are a legal document routing agent. Select the most relevant skills."
- User message: manifest (name + description per line) + matter summary
- Enforces JSON response: `{"selected": ["name1", "name2"], "unmatched": ["name3"]}`
- `unmatched`: names the LLM wanted but don't exist on disk (filtered by the caller)
- Returns `{"selected": [], "unmatched": []}` on any exception (never raises)

### `LexConfig` changes

```python
skill_router_model: str = "openai/gpt-4.1-mini"
# Env var: LEX_SKILL_ROUTER_MODEL
# Change to any LiteLLM-compatible model string.
# Recommended: cheap, fast model — this is routing, not drafting.
```

---

## Section 3: Consensus + Gap Logging + Terminal Nudge

### Consensus (parallel union)

The router node runs all three sources and unions their results:

```python
llm_selected    = route_skills(matter_summary, manifest, config)["selected"]
string_matched  = _string_match_skill_name(matter_type)  # new helper: existing loader logic, returns name not body
forced          = state.get("forced_skill_names") or []

final_selection = deduplicated_union(llm_selected, string_matched, forced)
active_skill    = load_skill_stack(final_selection, bundled_dir, user_dir)
```

String-match is a **peer**, not a fallback. Skills from any source are included.

### Gap logging

`unmatched` names from the LLM response (skills it wanted but aren't on disk) are appended to `~/.lexagent/missing_skills.log`:

```
2026-06-10T14:32:01  matter="arbitration petition for construction dispute"  missing=["arbitration_petition"]
```

File is created on first write. One line per event. JSON-safe matter summary (truncated to 120 chars).

### Terminal nudge

Shown immediately after the router node completes, before the draft node starts. Uses `rich.panel.Panel` to stderr so it doesn't corrupt piped output:

```
╭─ Skill Gap Detected ──────────────────────────────────────────────╮
│  The router identified 1 skill not yet in your library:           │
│                                                                   │
│    arbitration_petition  — not found                             │
│                                                                   │
│  Drafting without it. To add this skill later:                   │
│    lex skill create arbitration_petition                         │
│  Or load an existing skill manually:                             │
│    lex skill load <name>   /  Telegram: /skill <name>            │
╰───────────────────────────────────────────────────────────────────╯
```

No nudge if no gaps. Nudge is informational — it does not pause or prompt the user.

---

## Section 4: Slash Commands (CLI + Telegram)

### New state field

```python
forced_skill_names: Optional[List[str]]  # Skills forced by --skill flag or /skill command
```

Set before the graph runs. The router node unions this with LLM + string-match selections.

### CLI — `lex skill` command group (new subcommand in `cli.py`)

```bash
lex skill list                           # Table: name | description | source (bundled/user)
lex skill load <name>                    # Print full skill body to terminal
lex skill create <name>                  # Scaffold new skill .md from template
lex draft "matter" --skill <name>        # Force-add one skill (repeatable)
lex draft "matter" --skill s138_complaint --skill bail_application
```

`--skill` is repeatable. Values are written to `forced_skill_names` before graph invocation.

`lex skill create <name>` writes a skeleton `.md` to `~/.lexagent/skills/<name>.md` with all required frontmatter fields pre-filled and `description: "TODO"`. Opens in `$EDITOR` if set.

### Telegram — dynamic slash commands

**Registered at bot startup** from the live skills manifest — so adding a new skill file automatically makes its command available without code change.

Commands registered:
```
/skill_list              → inline keyboard: all skill names + descriptions
/skill <name>            → load named skill into current session
/s138_complaint          → shorthand (skill name directly as command)
/bail_application
/writ_petition
/written_statement
... (one per skill on disk)
```

Dynamic registration uses `bot.set_my_commands()` at startup with the manifest. Shorthand commands (`/s138_complaint`) are registered alongside `/skill <name>` for discoverability.

**Behaviour in both interfaces:** additive, not override. Manually selected skills are unioned with the router's output. The lawyer supplements the router — they don't replace it.

---

## Data Flow Summary

```
State fields written by skill_router node:
  active_skill        — stacked skill body (read by draft node, unchanged contract)
  active_skill_name   — comma-joined display names (e.g. "S.138 Complaint, Bail Application")
  selected_skill_names — list of names actually loaded (for audit/debugging)
  forced_skill_names  — set externally (CLI/Telegram), read by router, preserved in state
```

---

## Files Changed

| File | Change |
|------|--------|
| `lexagent/nodes/skill_router.py` | **New** — router node |
| `lexagent/skills/loader.py` | Add `build_skills_manifest()`, `route_skills()`, update `_parse_frontmatter()` |
| `lexagent/config.py` | Add `skill_router_model` field |
| `lexagent/state.py` | Add `forced_skill_names`, `selected_skill_names` fields |
| `lexagent/graph.py` | Insert `skill_router` node, update edges |
| `lexagent/cli.py` | Add `skill` command group + `--skill` flag on `draft` |
| `lexagent/gateway/telegram.py` | Dynamic command registration + `/skill` handler |
| `lexagent/skills/*.md` | Add `description` field to all frontmatter |

---

## What Does NOT Change

- `draft.py` — reads `state["active_skill"]` as before, zero changes
- `load_skill_stack()` — called by router with the final name list, unchanged
- `load_skill()` — still used for string-match pass, unchanged
- All existing tests — router is additive; removing it degrades to current behaviour

---

## Testing

- Unit: `build_skills_manifest()` returns correct shape; `_parse_frontmatter()` extracts `description`
- Unit: `route_skills()` — mock LiteLLM response, verify filtering of non-existent skill names
- Unit: consensus union logic — LLM + string-match + forced → correct deduplicated list
- Unit: gap log — file created, correct format, truncation
- Integration: `lex skill list` output matches manifest
- Integration: `--skill` flag propagates to `forced_skill_names` in state
- Integration: nudge appears when `unmatched` is non-empty; absent when all skills found
