# LexAgent Enterprise Readiness Architecture — Phase 10

This document covers the enterprise-readiness features planned for Phase 10.
All designs are grounded in the current Phase 6 codebase and must extend
(not replace) the existing SQLite + markdown file infrastructure.

---

## Multi-Lawyer Workspace Architecture

### Design Philosophy

LexAgent is currently single-user (one lawyer, one `~/.lexagent` directory).
The multi-lawyer workspace adds a `workspace_id` layer that namespaces all data
without requiring a new database engine. SQLite with WAL mode handles concurrent
access for firms up to ~10 lawyers.

For 100+ lawyers, the brief's Section 25 recommends PostgreSQL + pgvector.
Do not build that now.

### Workspace Identity Model

```
workspace/
├── {workspace_id}/
│   ├── SOUL.md              # workspace-level defaults (firm name, court preferences)
│   ├── members.yaml         # {user_id: {name, email, role, telegram_id}}
│   ├── matters/
│   │   └── {matter_id}/
│   │       ├── MEMORY.md
│   │       ├── state.json
│   │       └── owner: {user_id}
│   └── clients/
│       └── {client_id}/
│           └── MEMORY.md
```

A solo lawyer's existing `~/.lexagent` maps to `workspace_id="solo"` with no change to
current behaviour. The solo path is the default and requires no config change.

### New LexState Fields

| Field | Type | Source | Effect |
|-------|------|--------|--------|
| `workspace_id` | `Optional[str]` | `LexConfig.workspace_id` or CLI `--workspace` | Scopes all memory reads/writes |
| `user_id` | `Optional[str]` | `LexConfig.user_id` or CLI `--user` | Identifies which lawyer is acting |
| `user_role` | `Optional[str]` | `members.yaml` lookup by `user_id` | Controls what output is shown |

### Role Model

| Role | Can do | Cannot do |
|------|--------|-----------|
| `owner` | All operations; create/delete matters; add members | — |
| `senior` | Draft, review, approve, assign to juniors | Cannot delete workspace |
| `junior` | Draft, view assigned matters | Cannot approve for filing; cannot see other juniors' matters |
| `paralegal` | View matters, add notes to MEMORY.md | Cannot run drafts or approve |

### Data Isolation Enforcement

Every memory read/write call is wrapped with a workspace+user scope check:

```python
# memory/matter_memory.py — extended signature
def load_matter_memory(matter_id: str, workspace_id: str = "solo", user_id: str = None) -> str:
    # Resolve path: ~/.lexagent/workspaces/{workspace_id}/matters/{matter_id}/MEMORY.md
    path = _resolve_matter_path(workspace_id, matter_id)
    # Access check: if user_role == "junior", verify matter is assigned to user_id
    if not _can_access(workspace_id, user_id, matter_id):
        raise PermissionError(f"User {user_id} cannot access matter {matter_id}")
    return path.read_text() if path.exists() else ""
```

### `members.yaml` Schema

```yaml
# ~/.lexagent/workspaces/{workspace_id}/members.yaml
members:
  - user_id: "U001"
    name: "Advocate Sharma"
    email: "sharma@firm.com"
    role: "owner"
    telegram_id: 123456789
  - user_id: "U002"
    name: "Associate Gupta"
    email: "gupta@firm.com"
    role: "junior"
    telegram_id: 987654321
```

### Session Store Schema Changes

The `sessions` table in `sessions.db` gains `workspace_id` and `user_id` columns:

```sql
ALTER TABLE sessions ADD COLUMN workspace_id TEXT DEFAULT 'solo';
ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT NULL;
```

This is a schema migration (MED-09 type issue — adding columns to existing SQLite tables
requires careful handling if data exists). Migration script:

```python
# memory/session_store.py — add to init_db()
conn.execute("PRAGMA journal_mode=WAL")  # MED-09 fix
conn.execute("ALTER TABLE sessions ADD COLUMN workspace_id TEXT DEFAULT 'solo'"
             " IF NOT EXISTS")   # SQLite 3.37+
conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT NULL"
             " IF NOT EXISTS")
```

### CLI Changes for Multi-Lawyer

```bash
lex workspace create "Sharma & Associates"    # creates workspace, generates workspace_id
lex workspace add-member --email gupta@firm.com --role junior
lex workspace list-members
lex draft --workspace WS001 --user U002 "..."  # junior drafting
lex approve --matter-id M001                   # senior approval gate
```

### Telegram Multi-User Mapping

```python
# gateway/telegram.py — map Telegram user_id to workspace+user
def resolve_user(telegram_user_id: int) -> dict:
    # Query members.yaml for all workspaces where telegram_id matches
    # Returns: {workspace_id, user_id, user_role}
    ...
```

---

## Audit Trail Design

### Event Schema

Every LLM call generates one audit event. The audit log is write-once and append-only.

```sql
CREATE TABLE llm_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,           -- ISO 8601
    workspace_id    TEXT DEFAULT 'solo',
    user_id         TEXT,
    matter_id       TEXT,
    node_name       TEXT NOT NULL,           -- "intake", "draft", "cite", etc.
    model           TEXT NOT NULL,           -- "claude-sonnet-4-6"
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cache_read_tokens INTEGER,               -- Anthropic prompt cache hits
    latency_ms      INTEGER,
    input_hash      TEXT,                    -- SHA256 of full prompt
    output_hash     TEXT,                    -- SHA256 of full response
    error           TEXT,                    -- NULL if successful
    cost_usd        REAL                     -- computed at write time
);
CREATE INDEX idx_audit_matter ON llm_audit(matter_id);
CREATE INDEX idx_audit_workspace ON llm_audit(workspace_id, timestamp);
```

### Middleware Pattern

The audit logger wraps `get_llm()` in `nodes/_llm.py` as a decorator or context manager:

```python
# nodes/_llm.py — audit wrapper
import hashlib
import time

class AuditedLLM:
    """
    WHY: Wraps an LLM to log every call to the audit table.
    The pattern is transparent to node code — nodes call the same
    .ainvoke() method, and logging happens automatically.
    """
    def __init__(self, llm, config: LexConfig, node_name: str, matter_id: str):
        self._llm = llm
        self._cfg = config
        self._node_name = node_name
        self._matter_id = matter_id

    async def ainvoke(self, messages, **kwargs):
        start = time.monotonic()
        input_text = str(messages)
        try:
            result = await self._llm.ainvoke(messages, **kwargs)
            elapsed = int((time.monotonic() - start) * 1000)
            _write_audit_event(
                workspace_id=self._cfg.workspace_id or "solo",
                matter_id=self._matter_id,
                node_name=self._node_name,
                model=self._cfg.default_model,
                input_tokens=_count_tokens(input_text),
                output_tokens=_count_tokens(result.content),
                latency_ms=elapsed,
                input_hash=hashlib.sha256(input_text.encode()).hexdigest()[:16],
                output_hash=hashlib.sha256(result.content.encode()).hexdigest()[:16],
            )
            return result
        except Exception as e:
            _write_audit_event(..., error=str(e))
            raise
```

### Query Interface

```bash
lex audit show --matter-id M001          # all LLM calls for a matter
lex audit show --workspace WS001 --date 2026-08-01  # all calls on a date
lex audit cost --matter-id M001          # total cost for a matter
lex audit export --matter-id M001 --format csv  # export for billing
```

### Audit Table Query Examples

```sql
-- Total cost per matter
SELECT matter_id, SUM(cost_usd) as total_cost, COUNT(*) as calls
FROM llm_audit
GROUP BY matter_id
ORDER BY total_cost DESC;

-- Input token usage by node (to optimize prompt length)
SELECT node_name, AVG(input_tokens) as avg_input, AVG(output_tokens) as avg_output
FROM llm_audit
GROUP BY node_name;

-- Cache hit rate (Anthropic only)
SELECT
    COUNT(*) as total_calls,
    SUM(CASE WHEN cache_read_tokens > 0 THEN 1 ELSE 0 END) as cache_hits,
    CAST(SUM(cache_read_tokens) * 100.0 / SUM(input_tokens) AS INTEGER) as cache_hit_pct
FROM llm_audit
WHERE model LIKE 'claude%';
```

---

## PII Detection Pipeline

### Placement in Graph

PII detection runs BEFORE the draft node, AFTER the research node.
Research findings contain fetched judgment text (public data — low PII risk) but
the research query itself contains matter details (parties' names, addresses) that
should not appear verbatim in LLM calls for matters involving sensitive personal situations.

```
research → pii_redact → draft
```

`pii_redact` is flag-gated: `LEX_PII_REDACT=false` skips it via a conditional edge
(`route_after_research` returns "draft" directly).

### What is Detected

Indian-specific PII patterns:

| PII Type | Regex Pattern | Replacement |
|---------|--------------|-------------|
| Aadhaar number | `\b\d{4}[ -]?\d{4}[ -]?\d{4}\b` | `[REDACTED:AADHAAR]` |
| PAN number | `[A-Z]{5}\d{4}[A-Z]` | `[REDACTED:PAN]` |
| Indian mobile | `[+91 ]{0,4}[6-9]\d{9}` | `[REDACTED:PHONE]` |
| Indian address | postal code + street pattern | `[REDACTED:ADDRESS]` |
| Bank account | `\b\d{9,18}\b` near "account"/"a/c" | `[REDACTED:BANK_ACCT]` |

**What is NOT redacted:**
- Party names (e.g., "ABC Ltd v. XYZ Developers") — these appear in public court records
- Advocate names and bar numbers — professional identification, not personal PII
- Court names and case numbers — public record identifiers
- Citation strings — entirely public

### PII Node Implementation

```python
# nodes/pii_redact.py
import re

_PII_PATTERNS = [
    (re.compile(r'\b\d{4}[ -]?\d{4}[ -]?\d{4}\b'), '[REDACTED:AADHAAR]'),
    (re.compile(r'[A-Z]{5}\d{4}[A-Z]'), '[REDACTED:PAN]'),
    # ... other patterns
]

async def run(state: LexState) -> dict:
    """
    WHY: PII is stripped before any text reaches the LLM.
    This is especially important for research_findings which may contain
    excerpts from judgments that include witness Aadhaar numbers,
    victim phone numbers in criminal matters, etc.
    """
    try:
        redaction_log = []
        clean_findings = []

        for finding in (state.get("research_findings") or []):
            clean_text, log = _redact_text(finding.get("full_text", ""))
            clean_findings.append({**finding, "full_text": clean_text})
            redaction_log.extend(log)

        clean_input, input_log = _redact_text(state.get("user_input", ""))
        redaction_log.extend(input_log)

        return {
            "research_findings": clean_findings,
            "user_input": clean_input,
            "pii_redaction_log": redaction_log if redaction_log else None,
        }
    except Exception as e:
        return {"error": str(e)}

def _redact_text(text: str) -> tuple[str, list]:
    log = []
    for pattern, replacement in _PII_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            log.extend({"type": replacement, "count": len(matches)})
            text = pattern.sub(replacement, text)
    return text, log
```

### PII Confirmation Gate

When `LEX_PII_CONFIRM=true`, the pii_redact node uses LangGraph `interrupt()` to show
the redaction log to the lawyer before proceeding:

```python
# nodes/pii_redact.py — interrupt pattern
from langgraph.types import interrupt

if cfg.pii_confirm and redaction_log:
    # LANGGRAPH: interrupt() pauses graph execution and returns current state to caller.
    # Caller (CLI or Telegram handler) displays the log and waits for "confirm" or "cancel".
    human_decision = interrupt({
        "pii_redaction_log": redaction_log,
        "message": f"Detected {len(redaction_log)} PII items. Proceed with redaction?"
    })
    if human_decision.get("action") == "cancel":
        return {"error": "PII redaction cancelled by lawyer"}
```

---

## Cost Tracking Design

### Price Table

Stored as YAML under `lexagent/data/llm_prices.yaml`:

```yaml
# lexagent/data/llm_prices.yaml
# Prices in USD per million tokens (input / output / cache_read)
# Updated manually when Anthropic changes pricing.
models:
  claude-sonnet-4-6:
    input_per_mtok: 3.00
    output_per_mtok: 15.00
    cache_read_per_mtok: 0.30   # 10% of input price
  claude-haiku-4:
    input_per_mtok: 0.25
    output_per_mtok: 1.25
    cache_read_per_mtok: 0.03
```

### Cost Computation

In `_write_audit_event()`, cost is computed at write time:

```python
def _compute_cost(model: str, input_tokens: int, output_tokens: int,
                  cache_read_tokens: int = 0) -> float:
    prices = _load_price_table()
    p = prices.get(model, prices.get("default", {}))
    cost = (
        (input_tokens - cache_read_tokens) * p.get("input_per_mtok", 3.0) / 1_000_000
        + output_tokens * p.get("output_per_mtok", 15.0) / 1_000_000
        + cache_read_tokens * p.get("cache_read_per_mtok", 0.3) / 1_000_000
    )
    return round(cost, 6)
```

### Per-Matter Cost Report

```
Matter M001: Draft — Injunction Application
─────────────────────────────────────────────
Node            Calls   Input tokens   Output tokens   Cost (USD)
──────────────────────────────────────────────────────────────────
intake             2      1,240          340            $0.0087
research           1        890           45            $0.0027
draft              1      3,450        2,100            $0.0420
cite               0          0            0            $0.0000
review             0          0            0            $0.0000
──────────────────────────────────────────────────────────────────
TOTAL              4      5,580        2,485            $0.0534
Cache savings:    $0.0123 (18.7% reduction from prompt caching)

Equivalent in INR at ₹83/USD: ₹4.43
```

### INR Display

Indian lawyers think in rupees. Add a `LEX_DISPLAY_CURRENCY` config flag:

| Flag | Default | Effect |
|------|---------|--------|
| `LEX_DISPLAY_CURRENCY` | `"INR"` | Display cost in INR using `LEX_USD_INR_RATE` |
| `LEX_USD_INR_RATE` | `83.0` | USD to INR conversion rate |

---

## White-Label Configuration System

### Current Problem

`docx_writer.py` line 102 hardcodes `"Generated by LexAgent | Phase 5 draft — verify citations before filing"` in the document footer. This cannot be submitted to court.

### SOUL.md Extension

Add firm fields to the SOUL.md template in `memory/soul.py:SOUL_TEMPLATE`:

```markdown
## Firm Details
**Firm Name:** [e.g., Sharma & Associates, Advocates]
**Firm Address Line 1:** [Building, Street]
**Firm Address Line 2:** [City, State, PIN]
**Firm Phone:** [+91-...]
**Firm Email:** [info@firma.com]
**Firm PAN:** [optional]
**Letterhead Template:** [path to .docx letterhead template, optional]
```

### docx_writer.py Changes

```python
# tools/docx_writer.py — white-label footer
def _add_footer(doc, soul: dict):
    firm_name = soul.get("firm_name", "")
    firm_address = soul.get("firm_address_line1", "")
    if firm_name:
        footer_text = f"{firm_name} | {firm_address} | Draft — verify before filing"
    else:
        footer_text = "Draft generated by LexAgent — verify citations before filing"
    # Add to doc.sections[0].footer
    ...
```

### Letterhead Template Overlay

When `soul.get("letterhead_template")` is set, `write_docx()` opens the lawyer's
existing letterhead `.docx`, inserts the draft content into the body, and saves.
This uses `python-docx`'s document merge pattern.

```python
# tools/docx_writer.py — letterhead overlay
def write_docx(state: LexState, output_path: str) -> str:
    soul = state.get("lawyer_soul") or {}
    letterhead_path = soul.get("letterhead_template")

    if letterhead_path and Path(letterhead_path).exists():
        # Open letterhead template, insert content after last firm detail paragraph
        doc = Document(letterhead_path)
        _append_draft_to_template(doc, state)
    else:
        doc = Document()
        _build_document_from_scratch(doc, state, soul)

    doc.save(output_path)
    return output_path
```

### Config Flags for White-Label

| Flag | Default | Effect |
|------|---------|--------|
| `LEX_FIRM_LETTERHEAD` | `""` | Path to .docx letterhead template |
| `LEX_SUPPRESS_LEXAGENT_FOOTER` | `False` | Remove all LexAgent branding from output |
| `LEX_DRAFT_WATERMARK` | `True` | Add "DRAFT — verify before filing" watermark |

**Opinion:** `LEX_SUPPRESS_LEXAGENT_FOOTER=True` should require explicit opt-in.
The watermark (`LEX_DRAFT_WATERMARK`) should never be suppressed —
filing an unreviewed AI draft without a watermark is a liability risk.

---

## Dependency Table — Critical Fixes vs Features

This table answers: "Does this feature depend on a CRIT fix landing first?"

| Feature | Depends on CRIT-01 | Depends on CRIT-02 | Depends on CRIT-03 |
|---------|-------------------|-------------------|-------------------|
| Telegram gateway | No | Yes (RAPTOR crash risk) | No |
| Contract review | No | No | No |
| Re-ranker wiring (HIGH-01) | Yes (score check is same fix) | No | No |
| Hearing brief generator | No | No | **YES** (reads MEMORY.md) |
| Last-hearing memory bridge | No | No | **YES** |
| Cross-matter client intelligence | No | No | **YES** |
| Output versioning | No | No | **YES** |
| Citation chain tracer | **YES** (grounding must be reliable) | No | No |
| Ratio decidendi extractor | No | **YES** (research_findings mutations must be clean) | No |
| Contradiction detector | **YES** | **YES** | No |
| Hierarchical PageIndex | **YES** (retrieval overhaul) | No | No |
| Multi-lawyer workspace | No | No | **YES** (memory scoping) |
| Audit trail | No | No | No |
| PII detection | No | No | No |
| Cost tracking | No | No | No |
| White-label config | No | No | No |
| Court fee calculator | No | No | No |
| Limitation deadline alert | No | No | No (uses limitation_analysis, not memory) |
| Filing checklist | No | No | No |

**Summary:** CRIT-03 is the most blocking critical fix — it gates 5 features.
CRIT-01 gates 3 features (citation quality chain).
CRIT-02 gates 2 features (anything building on clean research_findings).

All three CRIT fixes must land in the Pre-Phase 7 sprint.
