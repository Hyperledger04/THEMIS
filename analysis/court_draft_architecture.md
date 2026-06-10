# Court-Ready Draft System — Architecture

_Proposed architecture for producing court-fileable output from LexAgent. Separated into distinct layers, each with a single responsibility. No code here — architecture only._

_Read alongside `draft_quality_gaps.md` (the problems this solves) and `formatting_engine.md` (Layer C detail)._

---

## The Core Principle

A court filing is not a document. It is an **assembly** of:
1. Verified typed facts
2. Section ordering rules specific to the document type
3. Format conventions specific to the court
4. Multiple sub-documents (complaint + affidavit + witness list + exhibit list + vakalatnama)
5. No internal lawyer notes

Current LexAgent conflates all five into one monolithic LLM call that produces one monolithic text blob. The proposed architecture separates them.

---

## Six Layers

```
Layer A — Matter Facts Store
    ↓
Layer B — Pleading Schema Registry
    ↓
Layer C — Court Profile Engine  ← lawyer fills this at setup wizard
    ↓
Layer D — Section Renderer  ← LLM + template-rendered sections
    ↓
Layer E — Post-Draft Structural Review
    ↓
Layer F — Filing Package Builder
```

Each layer has a single responsibility. Changing court format (Layer C) does not touch content (Layer A). Changing document type (Layer B) does not touch formatting (Layer C). The LLM lives in Layer D only.

---

## Layer A — Matter Facts Store

**Responsibility:** Hold the verified, structured facts of the matter as typed data — not as prose.

**Problem it solves:** The LLM currently re-derives facts from prose at every step. The draft prompt says "based on the user's brief, the parties are..." — the LLM re-reads the brief and re-extracts. If the brief mentions "Mrs. Shilpy Yadav" in one place and "Shilpy" in another, the LLM may use both forms. A typed Facts Store is the single source of truth.

**What it holds (for S.138 complaint):**
```python
class S138Facts:
    # Parties
    complainant_name: str           # "M/s. Pinnacle Systems"
    complainant_representative: str # "Sh. Ankush Sareen"
    complainant_address: str
    accused: list[AccusedParty]     # [{name, address, role: "proprietor/partner/director"}]
    accused_entity_type: str        # "individual" | "firm" | "company"

    # Transaction
    transaction_date: date
    invoice_number: str
    goods_description: str
    invoice_amount: Decimal         # ₹1,07,405

    # Payments
    part_payments: list[Payment]    # [{date, amount}]
    outstanding_amount: Decimal     # invoice_amount - sum(part_payments)

    # Cheque
    cheque_number: str
    bank_name: str
    branch_name: str
    account_number: str
    cheque_amount: Decimal          # ₹1,07,405
    cheque_date: date

    # Dishonour
    first_dishonour_date: date
    first_return_memo_number: str
    first_dishonour_reason: str     # "Drawers Signature Differs"
    second_dishonour: bool
    second_dishonour_date: date | None
    second_return_memo_number: str | None

    # Notice
    notice_date: date
    notice_modes: list[str]         # ["Speed Post", "WhatsApp", "E-mail"]
    notice_compliance_deadline: date  # notice_date + 15 days
    accused_complied: bool          # False

    # Computed fields (not LLM-generated)
    limitation_deadline: date       # notice_compliance_deadline + 30 days
    prayer_fine_amount: Decimal     # cheque_amount × 2
    presenting_bank_branch: str     # For S.142(2) jurisdiction
    court_jurisdiction: str         # GBN CJM if presenting bank in GBN

    # Exhibit registry (canonical, before drafting)
    exhibits: dict[str, str]        # {"invoice": "EX-CW1/A", "cheque": "EX-CW1/B", ...}
```

**Integration with current code:**
- `LexState` already has many of these fields scattered across `matter_type`, `parties`, `key_clauses`, `purpose`
- The upgrade is: extract these fields into a typed Pydantic model during intake, validate them, compute derived fields (limitation_deadline, prayer_fine_amount) arithmetically
- Store in `LexState["matter_facts"]` as a serialized dict
- All downstream nodes read from `matter_facts`, not from the raw `user_input` prose

**Note on V3 alignment:** Layer A is the seed of the `Matter Workspace` in V3 Phase 2. The typed `Fact`, `Party`, `ChronologyItem` models in `LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md §6` are the full implementation; Layer A here is the minimum viable version for Phase 0 court-ready drafts.

---

## Layer B — Pleading Schema Registry

**Responsibility:** Define, for each document type, the required sections in order, their names, which are mandatory vs optional, and what facts they depend on.

**Problem it solves:** Structure is currently 100% LLM-generated. Nothing in the pipeline enforces that a complaint has a Cause of Action paragraph. Nothing prevents the LLM from inventing section names. Nothing prevents sections from appearing in the wrong order.

**What it is:** A YAML or Python dict per document type (see `pleading_blueprints.md` for full schemas).

**Example schema (S.138 Complaint, abbreviated):**
```yaml
s138_complaint:
  party_labels:
    filer: Complainant
    opposing: Accused
  required_sections:
    - id: court_header
      source: court_profile       # rendered from court profile, not LLM
    - id: cause_title
      source: template            # rendered from facts, not LLM
    - id: para_transaction
      source: llm                 # LLM-generated narrative
      required_facts: [transaction_date, invoice_number, invoice_amount]
    - id: para_cheque
      source: template            # facts → structured prose, not LLM
      required_facts: [cheque_number, cheque_amount, bank_name]
    - id: para_s141_liability
      source: llm
      condition: "accused_entity_type != 'individual'"
    - id: cause_of_action
      source: template
      required_facts: [cause_of_action_date]
    - id: jurisdiction
      source: template
      required_facts: [presenting_bank_branch, court_jurisdiction]
      cites: "S.142(2) NI Act"
    - id: limitation
      source: template
      required_facts: [limitation_deadline]
      cites: "S.142(b) NI Act"
    - id: prayer
      source: template
      required_facts: [cheque_amount, prayer_fine_amount]
  sub_documents:
    - affidavit_evidence
    - witness_list
    - list_of_documents
    - vakalatnama
```

**Section sources:**
- `court_profile` — rendered entirely from the court profile (Layer C), no LLM
- `template` — rendered from the facts model (Layer A) using a Jinja-style template, no LLM
- `llm` — LLM-generated prose, with the facts model injected as structured context

**Key insight:** Only narrative sections (transaction story, dishonour circumstances, accused's conduct) need the LLM. Structural sections (court header, cheque particulars, cause of action, jurisdiction, limitation, prayer) can be rendered deterministically from typed facts. This reduces LLM variance in the sections that matter most procedurally.

**Integration:**
- Skills (`lexagent/skills/*.md`) currently encode this as free text. The schema registry formalizes it.
- The review node (Layer E) uses the registry to verify section presence.
- The filing package builder (Layer F) uses the `sub_documents` list to know what to generate.

---

## Layer C — Court Profile Engine

**Responsibility:** Hold per-court formatting and structural conventions. Decouple content from presentation.

**Problem it solves:** The same S.138 matter can be filed in GBN CJM, Delhi HC, or Punjab HC. The facts are identical. The format is different. Currently `docx_writer.py` has one hardcoded format for all courts.

**Full design:** See `formatting_engine.md`.

**Key insight — Lawyer-defined at setup, not developer-maintained:**
Instead of a developer-maintained YAML library for every Indian court, the setup wizard (`lex setup`) asks the lawyer for their formatting preferences once. This is stored in `~/.lexagent/SOUL.md` under `## Court Preferences`. The `docx_writer.py` reads from SOUL.

This is better than a developer-maintained library because:
- The lawyer who practises in GBN CJM knows GBN CJM conventions better than any developer
- Covers courts the developer has never seen
- Scales to any jurisdiction globally
- One-time setup; the lawyer owns it
- Judge-specific and clerk-specific conventions can be captured

---

## Layer D — Section Renderer

**Responsibility:** Given a section schema entry + facts + court profile → render that section as correctly formatted prose.

**Problem it solves:** The current draft node uses one monolithic LLM call to generate the entire document. This means: (a) the LLM must remember all structural rules at once, (b) early sections can affect late sections inconsistently, (c) template-renderable sections go through the LLM unnecessarily.

**Two types of sections:**
1. **Template-rendered:** Court header, cause title, cheque particulars, cause of action, jurisdiction, limitation, prayer. These have deterministic content from typed facts. Use a simple string template or Jinja2. Zero LLM tokens.
2. **LLM-rendered:** Transaction narrative, accused's conduct, demand notice circumstances. These require prose generation. LLM with structured context (facts model injected).

**How it works:**
```
for section in schema.required_sections:
    if section.condition and not evaluate(section.condition, facts):
        skip
    if section.source == "template":
        content = render_template(section.id, facts, court_profile)
    elif section.source == "llm":
        content = await llm_render(section.id, facts, court_profile, retrieved_reference)
    sections.append(content)
assembled_document = join(sections)
```

**RAG over reference documents (Pivot 2):**
For LLM-rendered sections, inject a retrieved reference from the lawyer's past filings at the section level, not the document level. "Here is how you rendered the transaction narrative in a past S.138 complaint filed in GBN CJM." The LLM mirrors the tone and structure of the lawyer's own work.

This is the mechanism for `lex add-reference <file.docx> --type s138_complaint` → Qdrant → `retrieve.py` query at draft time → injected per LLM section.

**Integration with current code:**
- Current `nodes/draft.py` is the monolithic version of Layer D
- The upgrade is: restructure `draft.py` to iterate over schema sections, call `_render_section()` per section, accumulate results
- LLM calls happen only for `source == "llm"` sections — typically 3–5 sections per document instead of one call for the whole document
- This actually reduces token usage because template-rendered sections are free

---

## Layer E — Post-Draft Structural Review

**Responsibility:** After all sections are rendered, verify the assembled document against the schema. Block the output if mandatory sections are missing.

**Problem it solves:** The current review node (`nodes/review.py:44–79`) only checks word count and citation verification. A complaint with no Cause of Action, no Jurisdiction, and no proper Prayer passes review without warning.

**What it checks:**
1. All required sections from the schema are present (by section ID or keyword search in content)
2. Sections appear in the correct order
3. All fact dependencies of each section are populated (no `[INSERT FACT]` placeholders)
4. Exhibit labels are consistent across complaint body, affidavit, and list of documents
5. Prayer contains the correct statutory amounts (for S.138: prayer_fine_amount = cheque_amount × 2)
6. No lawyer working notes in the filing body (check for risk flag keywords: "HIGH RISK", "MEDIUM RISK", "Generated by LexAgent", "Matter ID:")
7. Party labels are consistent with matter_type (Complainant/Accused for criminal, not Petitioner/Respondent)

**Output:** Structured `StructuralReviewResult`:
```python
class StructuralReviewResult:
    passed: bool
    missing_sections: list[str]
    ordering_errors: list[str]
    placeholder_leakage: list[str]    # "[INSERT...]" found in body
    exhibit_inconsistencies: list[str]
    lawyer_note_leakage: list[str]    # risk flags found in body
    party_label_errors: list[str]
```

If `passed=False` on a P0 check (lawyer notes, missing mandatory sections), block the output and return error to draft node for re-generation.

**Integration:**
- Extend `nodes/review.py` — add structural check after current word count check
- Read schema from Pleading Schema Registry (Layer B) based on `state["matter_type"]`

---

## Layer F — Filing Package Builder

**Responsibility:** Assemble the complete filing packet — not just the main document but all sub-documents — into a named output folder.

**Problem it solves:** `docx_writer.py` produces one monolithic .docx with lawyer notes embedded. A filing requires 4–6 separate documents.

**Output structure:**
```
output/{matter_id}/{date}/
    complaint.docx            ← court header, formal cause title, all required sections
    affidavit_evidence.docx   ← sworn testimony, first person, by complainant
    witness_list.docx         ← CW-1 + supporting witnesses
    list_of_documents.docx    ← exhibit register with canonical labels
    vakalatnama.docx          ← power of attorney (to be printed and signed)
    lawyer_notes.docx         ← Plain English Summary + Risk Assessment (NOT filed)
```

**Sub-document generation:**
- `complaint.docx` — from assembled sections (Layers B + D)
- `affidavit_evidence.docx` — second LLM call with instruction: "Restate the complaint facts in 12–14 numbered first-person paragraphs as sworn testimony. Reference each exhibit by its canonical label from the registry."
- `witness_list.docx` — template-rendered from facts: CW-1 is always the complainant; add bank officials if return memo authenticity is likely to be contested
- `list_of_documents.docx` — template-rendered from the exhibit registry (Layer A)
- `vakalatnama.docx` — template with lawyer's name/enrollment/address from SOUL.md + blank client signature block
- `lawyer_notes.docx` — the Plain English Summary and Risk Assessment from `draft_output` (everything after the `---` separator), routed here instead of into the filing

**Integration with current code:**
- `tools/docx_writer.py` → refactor into `tools/filing_package/`
  - `complaint_writer.py` — current docx_writer logic but with proper header
  - `affidavit_writer.py` — new
  - `ancillary_writer.py` — witness list, exhibit list, vakalatnama
  - `lawyer_notes_writer.py` — client summary and risk assessment
  - `package_builder.py` — orchestrates all writers, returns folder path
- `nodes/review.py` → triggers `package_builder.build_package()` instead of `write_docx()`

---

## How the Layers Work Together for S.138 Complaint

```
1. Intake extracts: parties, cheque facts, dishonour, notice, accused_entity_type
   → Layer A builds Matter Facts Store (typed, with computed fields)

2. Intake identifies matter_type = "s138_complaint"
   → Layer B loads the S.138 Complaint schema (required sections, sub-documents, exhibit registry)

3. Setup wizard has stored court preferences in SOUL.md
   → Layer C loads Court Profile (formal court name, exhibit label format, party labels)

4. retrieve.py queries Qdrant for past S.138 complaints filed by this lawyer
   → Layer D renders each section:
       - court_header: template ("IN THE COURT OF THE CHIEF JUDICIAL MAGISTRATE...")
       - cause_title: template (from party facts)
       - para_transaction: LLM (narrative, with past filing as reference)
       - para_s141_liability: LLM (conditional — fires because accused is proprietor)
       - jurisdiction: template (S.142(2) → presenting bank branch → GBN → GBN CJM)
       - limitation: template (30 days from notice_compliance_deadline)
       - prayer: template (cheque_amount × 2 = ₹2,14,810)

5. Layer E checks assembled document:
   ✓ All required sections present
   ✓ No "[INSERT...]" placeholders
   ✓ No "HIGH RISK" flags in body
   ✓ Exhibit labels consistent (EX-CW1/A throughout)
   ✓ Prayer amount = ₹2,14,810 (matches cheque_amount × 2)

6. Layer F builds filing packet:
   complaint.docx + affidavit_evidence.docx + witness_list.docx +
   list_of_documents.docx + vakalatnama.docx + lawyer_notes.docx
```

---

## What This Architecture Does NOT Require

- **Harvey-style subagents** — this is a structured pipeline, not a multi-agent system. The LLM is called for narrative sections only.
- **New database tables** — Layer A can start as a Pydantic model in `LexState["matter_facts"]`, not a Postgres table. The V3 matter workspace tables are the long-term home.
- **New graph nodes** — Layer D can be implemented as a restructured `draft.py`, not a new node. Layer F can be implemented as a restructured `docx_writer.py`.
- **New infrastructure** — Qdrant already exists for Pivot 2's reference store. SQLite already exists for past drafts.

The architecture is a refactor of what already exists, not a rebuild.
