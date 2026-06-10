# Draft Pipeline — Current State Trace

_Generated as part of Phase 0: Court-Ready Drafting Engine. Read alongside `draft_delta.md` and `draft_quality_gaps.md`._

---

## Pipeline Map

```
user_input (matter brief)
    │
    ▼
INTAKE NODE          nodes/intake.py:240–362
    │  Extracts: matter_type, parties, jurisdiction, purpose,
    │            key_clauses, tone_preference, active_skill
    │  No formatting. No structure. No court logic.
    ▼
RESEARCH NODE        nodes/react_research.py:219–310
    │  Kanoon API + optional Tavily web search
    │  Outputs: research_findings[], statutes_cited[]
    │  No formatting. No structure.
    ▼
RETRIEVE NODE        nodes/retrieve.py:61–120
    │  Loads: template .md + up to 2 past drafts from SQLite
    │  Templates are narrative hints, not enforced schemas
    │  Outputs: retrieval_chunks[]
    ▼
DRAFT NODE           nodes/draft.py:289–415
    │  Single monolithic LLM call
    │  Inputs: all intake fields + research + templates + skill + SOUL.md
    │  Outputs: draft_output (includes Plain English Summary +
    │           Risk Assessment — these MUST NOT be in a court filing)
    ▼
CITE NODE (conditional)   nodes/cite.py:73–234
    │  Grounds citations via HybridRetriever (BM25 + Qdrant)
    │  Optional LLM re-ranker
    │  No formatting.
    ▼
REVIEW NODE          nodes/review.py:44–101
    │  Checks: word count vs jurisdiction limits, citation verification
    │  Does NOT check: section presence, structure, party labels,
    │                  exhibit consistency, court header
    ▼
DOCX WRITER          tools/docx_writer.py:24–141
    │  Writes ALL of draft_output to .docx — no separator parsing
    │  Includes the lawyer's Plain English Summary and Risk Assessment
    │  Title block: matter_type.title() → "Legal Document" (not a court header)
    │  Party block: guesses label from dict keys (plaintiff/petitioner)
    │  Body: split on double newlines, each paragraph → justified Times New Roman 12pt
    │  Margins: 1.5" left, 1" others (hardcoded, not court-profile-aware)
    ▼
Output: single .docx file with lawyer notes embedded
```

---

## Stage-by-Stage Detail

### Stage 1 — User Input

**Entry point:** `LexState["user_input"]`  
**File:** `lexagent/state.py`

Raw matter brief as a string. No parsing, no validation. Everything downstream derives from this text.

---

### Stage 2 — Intake Node

**File:** `lexagent/nodes/intake.py:240–362`  
**Function:** `async def run(state: LexState) -> dict`

**What it extracts:**
- `matter_type` — e.g., "s138_complaint", "writ_petition", "bail_application"
- `parties` — dict: `{plaintiff, defendant}` or `{petitioner, respondent}` or `{complainant, accused}` — labels are LLM-guessed, not schema-enforced
- `jurisdiction` — free-text court name
- `purpose` — what document is needed
- `key_clauses` — specific reliefs
- `tone_preference` — "senior formal" | "plain commercial"
- `active_skill` — content of the matching .md skill file

**What it does NOT extract:**
- `accused_entity_type` (individual / company / firm) — needed for S.141 NI Act
- `court_formal_name` — needed for court header block
- `presenting_bank_branch` — needed for S.142(2) jurisdiction para
- `notice_compliance_deadline` — needed for limitation arithmetic
- Exhibit inventory — needed for exhibit registry

**Routing (graph.py:144–172):**
- `intake_complete=False` → END (return to user)
- `matter_type` in `_NO_RESEARCH_TYPES` → skip research → retrieve
- Otherwise → research

---

### Stage 3 — Research Node

**File:** `lexagent/nodes/react_research.py:219–310`  
**Function:** `async def run(state: LexState) -> dict`

Runs Kanoon API search and optional Tavily. Applies citation gate (every finding must have `title`, `url`, `citation`). Returns `research_findings[]` and `statutes_cited[]`.

No formatting. No structure. No court logic.

---

### Stage 4 — Retrieve Node

**File:** `lexagent/nodes/retrieve.py:61–120`  
**Function:** `async def run(state: LexState) -> dict`

Loads up to 8,000 chars of template content from `templates_index.json` and up to 2 past drafts from SQLite via BM25.

**Critical gap:** The template for S.138 matters is `templates/legal_notice_s138.md` — a **demand notice** template, not a complaint template. When a lawyer asks for an S.138 complaint, the retrieve node injects a demand notice as the structural reference.

No formatting. No structure enforcement.

---

### Stage 5 — Draft Node

**File:** `lexagent/nodes/draft.py:289–415`  
**Function:** `async def run(state: LexState) -> dict`

**This is where all structure and formatting decisions happen — inside the LLM.**

System prompt assembled from:
1. `lexagent/prompts/base_system.md` — identity + citation rules + **instructions to append Plain English Summary and Risk Assessment**
2. Active skill content (injected as a block)
3. SOUL.md lawyer identity

User-turn instruction includes:
- Matter type, parties, jurisdiction, purpose, key clauses, tone
- Research findings as a bulleted list (if present)
- Template reference: "Follow this structure and format exactly" (the wrong S.138 template)
- Up to 2 past-draft examples (first 800 chars each)

**The core problem:** `base_system.md:42–46` explicitly instructs:
> _"After the document, separated by `---`, provide a Plain English Summary (2–3 sentences). After the Plain English Summary, add a separate Risk Assessment section..."_

The LLM faithfully follows this instruction. The draft_output string therefore contains three sections: (a) legal document, (b) Plain English Summary, (c) Risk Assessment. All three are written to the .docx by docx_writer.

Returns: `draft_output` (full string including client-facing notes), `plain_english_summary` (extracted by regex).

---

### Stage 6 — Cite Node (conditional)

**File:** `lexagent/nodes/cite.py:73–234`  
**Function:** `async def run(state: LexState) -> dict`

Grounds citations via HybridRetriever. Output: `grounded_citations[]`, `unverified_citations[]`.

No formatting. No structure.

---

### Stage 7 — Review Node

**File:** `lexagent/nodes/review.py:44–101`  
**Function:** `async def run(state: LexState) -> dict`

**What it checks:**
- Word count vs jurisdiction-specific limits (injunction: 5000, writ: 8000, legal notice: 2000, plaint: 10000)
- Presence of unverified citations
- Non-empty draft

**What it does NOT check:**
- Presence of mandatory sections (CAUSE OF ACTION, JURISDICTION, LIMITATION, PRAYER)
- Section ordering
- Party label correctness
- Exhibit label consistency
- Presence of lawyer working notes (Plain English Summary, Risk Assessment, Matter ID) — these are not stripped
- Whether an affidavit is needed

Triggers `write_docx` if `docx_output_path` is set.

---

### Stage 8 — Docx Writer

**File:** `lexagent/tools/docx_writer.py:24–141`  
**Function:** `def write_docx(state: LexState, output_path: str) -> str`

**What it produces:**
1. Title block: `matter_type.title()` as Heading 1 — outputs "Legal Document", "Complaint", etc. — NOT a formal court header
2. Parties block: `parties.get("plaintiff") or parties.get("petitioner")` — label guessing, not schema-driven
3. Jurisdiction line: free-text, italic, centered
4. Body: `draft_output` split on double newlines — **includes Plain English Summary and Risk Assessment verbatim**
5. Citations appendix (if grounded_citations exist)
6. Matter metadata footer: `"Matter ID: {id} | Generated by LexAgent | Phase 5 draft — verify citations before filing"`

**Formatting (hardcoded):**
- Left margin: 1.5" — correct for Indian courts
- Font: Times New Roman 12pt — correct
- Double-spacing — correct
- No court-profile awareness: same format regardless of court

**Output:** Single .docx file. No filing packet. No lawyer_notes.docx separation.

---

## Where Each Concern Currently Lives

| Concern | Where it happens | Quality |
|---------|-----------------|---------|
| **Formatting** | `docx_writer.py` only — basic margins/font | Hardcoded, not court-aware |
| **Structure** | Inside LLM's `draft_output` | LLM-generated, zero enforcement |
| **Content** | `draft.py` LLM call | Good — grounded in research |
| **Court logic** | Skill `.md` files as text hints | Never verified or enforced |
| **Filing packet** | Not implemented | Missing entirely |
| **Exhibit labels** | LLM chooses — no registry | Inconsistent |
| **Affidavit** | Not generated | Missing entirely |
| **Lawyer notes separation** | Not implemented | Notes embedded in filing |
