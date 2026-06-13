# Indian Legal Document Formatter

Reformats any input (existing .docx, .pdf, or raw text) into a ready-to-use
Word document following Indian legal conventions and user-specified
instructions. Substantive content is preserved verbatim — only structure,
styling, numbering, and presentation are normalised.

## Step 0: Load Context

1. Check `LexState` for `lawyer_soul` (firm preferences). Apply the default
   "Indian Corporate Contract Style" unless the document is a pleading.
2. Check the current matter context for formatting overrides.
3. Apply every entry under `## Rules` in the Standing Rules section below.

## Step 1: Detect Document Type

Auto-detect the document family by scanning the first 2 pages:
- **Contract / Agreement** → "WHEREAS", "AGREEMENT", numbered clauses, defined
  terms, schedules, signature blocks
- **Pleading / Petition** → "IN THE COURT OF", cause title, numbered averments,
  verification, "MOST RESPECTFULLY SHOWETH"
- **Notice / Legal Notice** → "Through:", "Subject:", "Without Prejudice",
  advocate's reference
- **Opinion / Memorandum** → "Re:", "Issues for Consideration", "Analysis",
  "Conclusion"

State the detected type and confirm with the user before proceeding if
ambiguous.

## Step 2: Select Formatting Profile

Based on document type, load the relevant profile from the References section:
- Contract → Corporate Contract Style
- Pleading → Litigation Pleading Style
- Notice → Legal Notice Style

Each profile defines: font, spacing, margins, heading styles, clause
numbering, defined-term treatment, recital format, schedule formatting,
signature block, and page-number convention.

## Step 3: Build the Document

Use `write_docx` from `lexagent/tools/docx_writer.py`. Build in this order so
cross-references and TOC resolve correctly:

1. Set page setup (A4, margins per profile)
2. Define Word styles: Normal, Heading 1–4, Body, Recital, Definition,
   SignatureBlock, ScheduleTitle
3. Insert cause title / parties block / cover page as applicable
4. Insert auto-TOC field if user wants TOC
5. Insert recitals (WHEREAS clauses)
6. Insert numbered operative clauses — single multi-level list so
   cross-references auto-renumber
7. Bold-mark defined terms on first introduction; ensure all subsequent
   uses are consistent (case-sensitive)
8. Insert schedules/annexures with page break + Schedule heading style
9. Insert signature block (two-column table)
10. Add footer with "Page X of Y"
11. Replace hardcoded clause cross-refs with Word REF fields pointing to
    bookmarks on each clause

## Step 4: Legal Compliance Guardrails

These apply to every output without exception:

1. **Preserve original language** — Do not paraphrase, rewrite, or substantively
   edit clause text. Formatting only.
2. **Log structural changes** — Maintain a change log of renumbering, heading
   promotions, and term capitalisation changes.
3. **Flag uncertainty** — Tag `[REQUIRES VERIFICATION]` in the change log
   rather than guessing on ambiguous elements.
4. **No legal advice** — If a defined term is used before its definition, or a
   cross-reference points nowhere, log it; do not invent content.
5. **Attorney review note** — Always include `[REQUIRES ATTORNEY REVIEW BEFORE
   EXECUTION/FILING]` at the top of the change log.

## Step 5: Deliver

Save the final .docx to the matter's output directory via `write_docx`. Provide
a 3–5 line summary: document type, profile applied, notable changes, anything
flagged for review.
