# Formatting Engine

_How one matter renders into different court formats without changing its content. Separates Content (what happened) from Structure (section order) from Format (typography, headers, labels)._

---

## The Separation Principle

| Layer | What it is | Who defines it | Changes per? |
|-------|-----------|----------------|-------------|
| Content | Facts, arguments, citations | Lawyer + LLM | Matter |
| Structure | Section ordering + naming | Pleading Schema Registry | Document type |
| Format | Typography, margins, headers, labels | Court Profile | Court / lawyer preference |

Changing from GBN CJM to Delhi HC for the same S.138 matter should touch only Layer 3 (Format). The facts and the section structure are identical. Only the court name, exhibit label format, and cause title style differ.

Currently in LexAgent, all three layers are conflated inside the LLM call and `docx_writer.py`. This document proposes a Court Profile Engine that holds Layer 3.

---

## Architectural Pivot: Lawyer-Defined, Not Developer-Maintained

The original approach would have been a developer-maintained YAML library for every Indian court. This is impractical:
- India has 25 High Courts + hundreds of district courts + multiple tribunals
- Each HC bench has local conventions
- Individual judges have preferences that differ from the court's official rules
- The lawyer who appears in GBN CJM knows its conventions better than any developer

**The right approach:** The setup wizard (`lex setup`) asks the lawyer for their formatting preferences once. Stored in `~/.lexagent/SOUL.md` under `## Court Preferences`. The `docx_writer.py` (and eventually the Section Renderer) reads from SOUL.

The developer provides sensible defaults. The lawyer corrects them at setup. The system uses the lawyer's settings.

---

## Setup Wizard — Court Preferences Questions

Questions to add to `lex setup` (and the existing setup wizard in `lexagent/nodes/intake.py` / CLI):

```
COURT PREFERENCES SETUP
─────────────────────────────────────────────

1. What is your primary court of practice?
   (e.g., GBN CJM / Delhi HC / Allahabad HC / Punjab HC)
   → stored as: court_name_formal (full formal name)
                court_short_name (abbreviation)
                court_type: district_criminal | district_civil | high_court | supreme_court

2. What font do you prefer for court documents?
   [1] Times New Roman (most common, recommended)
   [2] Arial
   [3] Courier New
   [4] Other: ___
   → stored as: font_name

3. What font size? [1] 12pt (recommended)  [2] 14pt  [3] Other: ___
   → stored as: font_size

4. What line spacing? [1] Double (recommended)  [2] 1.5  [3] Single
   → stored as: line_spacing: "double" | "1.5" | "single"

5. What left margin? [1] 1.5 inch (recommended)  [2] 1 inch  [3] 2 inch
   → stored as: margin_left_inches

6. How do you number paragraphs?
   [1] 1.   2.   3.  (numeric dot, recommended for district courts)
   [2] (1)  (2)  (3) (bracket style)
   [3] 1)   2)   3)  (bracket after number)
   → stored as: para_numbering_style

7. What exhibit label format does your court use?
   [1] EX-CW1/A  EX-CW1/B  (district court witness-exhibit format, recommended)
   [2] Annexure P-1  P-2  (High Court petitioner annexure format)
   [3] Ex.P-1  Ex.P-2  (some district courts)
   [4] Annexure A  B  C  (generic)
   [5] Custom: ___
   → stored as: exhibit_label_format

8. How do you handle the Vakalatnama?
   [1] Include in filing packet, client signs before filing
   [2] File separately at court counter
   → stored as: vakalatnama_in_packet: true | false

9. How many sets/copies do you typically file?
   [1] 3 (original + 2)  [2] 4  [3] 5  [4] Other: ___
   → stored as: filing_copies

10. Paste an example cause title from your past filing:
    (This teaches the system your exact formatting style for cause titles)
    → stored as: cause_title_example
```

**SOUL.md section added by setup:**
```markdown
## Court Preferences

court_name_formal: "IN THE COURT OF THE CHIEF JUDICIAL MAGISTRATE, GAUTAM BUDH NAGAR AT GREATER NOIDA"
court_short_name: "GBN CJM"
court_type: district_criminal
font_name: "Times New Roman"
font_size: 12
line_spacing: double
margin_left_inches: 1.5
para_numbering_style: "numeric_dot"
exhibit_label_format: "EX-CW{witness}/{alpha}"
vakalatnama_in_packet: true
filing_copies: 4
cause_title_example: |
  M/s. Pinnacle Systems,
  a proprietary concern owned and operated by
  Sh. Ankush Sareen ...                          COMPLAINANT

                    VERSUS

  1. Mr. Santosh                                  ACCUSED
  2. Mrs. Shilpy Yadav                            ACCUSED
```

---

## Court Profile Data Model

The Court Profile is loaded from SOUL.md at draft/render time:

```python
@dataclass
class CourtProfile:
    # Identification
    court_name_formal: str      # Full formal name for header
    court_short_name: str       # Abbreviation for references
    court_type: str             # district_criminal | district_civil | high_court | sc

    # Typography
    font_name: str              # "Times New Roman"
    font_size: int              # 12
    heading_size: int           # 14
    line_spacing: str           # "double" | "1.5" | "single"
    para_spacing_after_pt: int  # 12

    # Margins (inches)
    margin_left: float          # 1.5
    margin_right: float         # 1.0
    margin_top: float           # 1.0
    margin_bottom: float        # 1.0

    # Header format
    header_style: str           # "centered_all_caps" | "bold_centered" | "left_aligned"
    header_repeat: bool         # True for HC; False for most district courts
    cause_title_example: str    # From setup wizard — mirrors lawyer's own style

    # Labels
    para_numbering_style: str   # "numeric_dot" | "bracket" | "bracket_after"
    exhibit_label_format: str   # "EX-CW{witness}/{alpha}" | "Annexure P-{n}" | etc.
    party_labels: dict          # {"s138_complaint": {"filer": "Complainant", "opposing": "Accused"}}

    # Filing logistics
    vakalatnama_in_packet: bool
    filing_copies: int
```

---

## How One Matter Renders Differently Across Courts

### Same S.138 matter — GBN CJM vs Delhi HC vs Punjab HC

**Court Header:**

GBN CJM:
```
IN THE COURT OF THE CHIEF JUDICIAL MAGISTRATE,
GAUTAM BUDH NAGAR AT GREATER NOIDA
```

Delhi HC:
```
IN THE HIGH COURT OF DELHI AT NEW DELHI
CRIMINAL JURISDICTION
```

Punjab & Haryana HC:
```
IN THE HIGH COURT OF PUNJAB AND HARYANA AT CHANDIGARH
CRIMINAL ORIGINAL JURISDICTION
```

**Exhibit Labels:**

| Court | Format | Example |
|-------|--------|---------|
| GBN CJM | EX-CW{witness}/{alpha} | EX-CW1/A |
| Delhi HC | Annexure P-{n} | Annexure P-1 |
| Punjab HC | Ex.P-{n} | Ex.P-1 |
| Some district courts | Annexure {alpha} | Annexure A |

**Cause Title Format:**

GBN CJM (criminal):
```
M/s. Pinnacle Systems ... Complainant
         versus
1. Mr. Santosh          ... Accused
2. Mrs. Shilpy Yadav    ... Accused
```

Delhi HC (criminal writ):
```
M/s. Pinnacle Systems                    ...Petitioner
         Versus
State of Delhi & Ors.                    ...Respondents
```

**Synopsis and List of Dates:**
- GBN CJM: Not required
- Delhi HC: Required (precede the body paragraphs)
- SC: Required, plus separate Index of Pleadings

**Affidavit:**
- District courts: Always standalone document
- Delhi HC: Sometimes in-text verification + standalone affidavit both required
- SC: Formal supporting affidavit with specific prescribed heading

---

## How `docx_writer.py` Should Use the Court Profile

**Current (hardcoded):**
```python
# docx_writer.py:43–60 — current
title_para = doc.add_heading(matter_type.title(), level=1)  # "Legal Document"
parties_para = doc.add_heading(f"{plaintiff}  v.  {defendant}", level=2)

# docx_writer.py:34–38 — margins hardcoded
section.left_margin = Inches(1.5)
```

**Proposed (profile-aware):**
```python
# Load court profile from SOUL.md at write time
profile = load_court_profile_from_soul()

# Court header — uses formal name, not matter_type
court_para = doc.add_paragraph(profile.court_name_formal)
apply_header_style(court_para, profile.header_style)  # centered_all_caps

# Cause title — uses profile's party labels + lawyer's cause_title_example as style guide
cause_title = render_cause_title(matter_facts, profile)
doc.add_paragraph(cause_title)

# Margins from profile
section.left_margin = Inches(profile.margin_left)
section.right_margin = Inches(profile.margin_right)

# Font and spacing from profile
def _set_font(para):
    for run in para.runs:
        run.font.name = profile.font_name
        run.font.size = Pt(profile.font_size)

def _set_spacing(para):
    para.paragraph_format.line_spacing = {
        "double": Pt(profile.font_size * 2),
        "1.5": Pt(profile.font_size * 1.5),
        "single": Pt(profile.font_size),
    }[profile.line_spacing]
```

---

## RAG Over Reference Documents (Pivot 2) — Format Intelligence

For sections that are LLM-generated (transaction narrative, grounds, accused conduct), inject the lawyer's own past filing for that document type + court as a structural reference.

**How it works:**
1. Lawyer runs: `lex add-reference COMPLAINT-138\ NI\ ACT\ \(2\).docx --type s138_complaint --court gbncjm`
2. The document is chunked and stored in Qdrant with metadata: `{doc_type: "s138_complaint", court: "gbncjm", lawyer_id: "..."}`
3. At draft time, `nodes/retrieve.py` queries Qdrant: `{"doc_type": "s138_complaint", "court": "gbncjm"}` → returns the top 2 most similar past filings
4. The retrieved document is injected into the LLM sections' context: _"Here is an example of how this lawyer has written an S.138 complaint for GBN CJM before. Mirror the section structure, cause title style, prayer wording, and exhibit labels."_
5. The LLM learns from the lawyer's own past work — not from developer-written templates

**What the LLM learns from the reference:**
- Tone and sentence structure (formal advocate prose vs plain language)
- Cause title format (exactly as the lawyer writes it)
- Prayer wording (including the "twice the cheque amount" specificity)
- Exhibit label format (EX-CW1/A or Annexure P-1 — whichever the lawyer uses)
- Section verbosity (concise 14 paras vs verbose 27 paras)

**Integration point:**
- `nodes/retrieve.py` already does BM25 over SQLite past drafts
- Upgrade: add Qdrant query with `doc_type` + `lawyer_id` metadata filter alongside the existing SQLite query
- The Qdrant collection (`reference_documents`) is separate from the existing `judgment_cache` collection
- Skills can declare `reference_collection: s138_complaints` in frontmatter; `nodes/retrieve.py` auto-fetches on skill load

---

## What Does NOT Change When Changing Court

When the same S.138 matter is re-rendered for a different court:
- All facts (amounts, dates, parties, cheque details) — unchanged
- All legal argument (S.141 liability, Laxmi Dyechem precedent) — unchanged
- Section structure (14 required sections in order) — unchanged
- All that changes: court name, party labels, exhibit label format, cause title style

This is the payoff of the separation principle. A lawyer who practises in both Delhi HC and GBN CJM changes one setting at the top of the SOUL.md — and the same matter generates two differently-formatted filing packets.
