"""
Phase 10 — 01: The Canonical Matter Workspace
==============================================
Run:  pip install pydantic
      python 01_matter_workspace.py

Today LexAgent keeps matter state in at least four places:
  - LexState TypedDict fields (in-memory, lost between runs)
  - ~/.lexagent/matters/{id}/MEMORY.md (unstructured markdown)
  - sessions.db (SQLite, full conversation logs)
  - LangGraph checkpoints (graph-internal, hard to query)

For a real law firm this is dangerous.  A lawyer should be able to ask:
  "Which facts in this matter are still disputed?"
  "Which authorities have we cited that are not yet verified?"
  "What is the current approved draft?"

None of these questions are answerable against the current scattered state.
V3 answers all of them with a single Postgres query.
"""

# ── SECTION 1: WHY SCATTERED STATE IS A LEGAL RISK ──────────────────────────
#
# Legal documents can be challenged on two grounds:
#   A) FACTUAL ERROR — the brief states something untrue
#   B) CITATION HALLUCINATION — the brief cites a case that does not exist,
#      or mis-states the holding of a real case
#
# Today's LexAgent has no structured defence against either:
#   - Facts extracted by the agent live in `research_findings` (a plain string)
#   - Authorities live in `statutes_cited` (another plain string)
#   - There is no status tracking: is this fact admitted or still alleged?
#   - There is no verification flag: did we actually confirm this citation exists?
#
# V3 solution: a Postgres-backed canonical matter workspace with:
#   - Structured Fact records with provenance and status
#   - Structured Authority records with treatment history and verified flag
#   - Versioned Draft records with approval status
#
# WHY Postgres and not LangGraph checkpoints?
# LangGraph checkpoints store the full state blob per graph run.
# They are optimised for "resume this run" — not for "query all disputed facts
# across all matters for this firm". Postgres gives you SQL.

import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError


# ── SECTION 2: PROVENANCE — WHERE DID THIS FACT COME FROM? ──────────────────
#
# Every Fact and Authority needs a provenance trail so a lawyer can answer:
# "Why does LexAgent believe this?" and "Should I trust this?"
#
# source_type options:
#   "user"     — lawyer typed this directly (highest trust)
#   "document" — extracted from an uploaded PDF/scan (high trust, but OCR errors possible)
#   "agent"    — inferred by the LLM (lower trust — must be verified)
#   "court"    — pulled from an official court portal (high trust)
#
# WHY the confidence field?
# When the agent extracts a date from a scanned document, confidence may be 0.7
# (OCR uncertainty). When the lawyer types a date, confidence is 1.0.
# A downstream citation node can refuse to use any fact with confidence < 0.8.

class Provenance(BaseModel):
    source_type: Literal["user", "document", "agent", "court"]
    source_id: Optional[str] = None    # e.g. document upload ID or session ID
    quote: Optional[str] = None        # verbatim text that supports this fact
    confidence: float = 1.0            # 0.0–1.0; agent extractions default to 0.75


# ── SECTION 3: FACT — A STRUCTURED LEGAL ASSERTION ──────────────────────────
#
# A Fact is any assertion about the matter that may appear in a pleading.
# Examples:
#   "The cheque was dated 12 March 2024."
#   "The defendant was the drawer of the cheque."
#   "The legal notice was served by registered post."
#
# WHY status as a Literal (not a free string)?
#   "alleged"  — asserted but not yet supported by evidence
#   "admitted" — opposing party has admitted this fact (no need to prove)
#   "disputed" — opposing party contests this; we need evidence
#   "proved"   — supported by documentary/oral evidence on record
#   "unknown"  — we have not yet determined the status
#
# Using a Literal forces every code path to use one of these values.
# A free string like "the defendant says it's false" would make
# database queries and risk analysis impossible.
#
# WHY does agent-generated fact default to "alleged"?
# The LLM is not a witness and has not seen the original documents.
# Calling an LLM output "proved" would be legally reckless.
# Defaulting to "alleged" means a lawyer must explicitly upgrade the status.

class Fact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    matter_id: str
    text: str
    status: Literal["alleged", "admitted", "disputed", "proved", "unknown"] = "alleged"
    provenance: list[Provenance] = []
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def is_safe_to_plead(self) -> bool:
        """
        A fact is safe to plead if it is at least 'alleged' (the default for
        lawyer-provided facts) and has at least one provenance entry.
        'unknown' facts must never appear in a pleading.
        """
        return self.status != "unknown" and len(self.provenance) > 0


# ── SECTION 4: AUTHORITY — A CASE, STATUTE, OR REGULATION ───────────────────
#
# An Authority is any legal source cited in support of a proposition.
# Examples:
#   Kesavananda Bharati v. State of Kerala, AIR 1973 SC 1461
#   Section 138, Negotiable Instruments Act, 1881
#   RBI Master Direction on KYC, 2016 (updated 2023)
#
# WHY type as a Literal?
#   "case"       — judicial precedent; binding or persuasive depending on court
#   "statute"    — act of Parliament or State Legislature
#   "regulation" — delegated legislation (rules, bye-laws)
#   "circular"   — regulatory guidance (RBI, SEBI, MCA); not binding but enforceable
#
# WHY treatment as a Literal?
#   "binding"      — this court is bound to follow it (same or higher court)
#   "persuasive"   — different jurisdiction or lower court; may be relied upon
#   "distinguished"— factually different; opponent will argue it doesn't apply
#   "overruled"    — subsequent bench has expressly overruled this authority
#   "unknown"      — we have not yet researched the treatment
#
# WHY verified: bool = False?
# LLMs hallucinate citations. An authority with verified=False must NOT be
# cited in any filed document. The cite node (lexagent/nodes/cite.py) sets
# verified=True only after confirming the case exists on Indian Kanoon.
# This is the single most important safety flag in the entire system.

class Authority(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: Literal["case", "statute", "regulation", "circular"]
    title: str
    citation: Optional[str] = None     # e.g. "AIR 1973 SC 1461"
    proposition: str                   # what legal point this authority stands for
    treatment: Literal[
        "binding", "persuasive", "distinguished", "overruled", "unknown"
    ] = "unknown"
    verified: bool = False             # MUST be True before appearing in any filing

    def is_safe_to_cite(self) -> bool:
        """
        An authority is safe to cite in a filed document only if:
        1. It has been verified against an authoritative source.
        2. It has not been overruled.
        An overruled authority cited as good law is professional misconduct.
        """
        return self.verified and self.treatment != "overruled"


# ── SECTION 5: DRAFT — A VERSIONED LEGAL DOCUMENT ───────────────────────────
#
# A Draft represents one version of one document (petition, notice, affidavit).
# Versions are tracked so the lawyer can compare v1 (agent output) with v3
# (after two rounds of review) without losing history.
#
# WHY status as a Literal?
#   "draft"        — agent-generated; not reviewed
#   "under_review" — lawyer is reviewing; edits in progress
#   "approved"     — lawyer has approved the content
#   "filed"        — document has been filed with the court/authority
#
# WHY does "filed" matter?
# Once a document is filed, it is part of the court record.
# The system must prevent any agent from silently editing a filed document.
# A filed Draft is immutable — a new version must be created if corrections needed.

class Draft(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    matter_id: str
    doc_type: str                      # "writ_petition" | "legal_notice" | "affidavit" etc.
    version: int = 1
    content: str
    status: Literal["draft", "under_review", "approved", "filed"] = "draft"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def can_be_edited(self) -> bool:
        """
        A filed document cannot be edited.  The agent must never attempt to
        update a filed Draft — it must create Draft(version=n+1, status='draft').
        """
        return self.status != "filed"


# ── SECTION 6: MATTER WORKSPACE — THE CANONICAL CONTAINER ───────────────────
#
# MatterWorkspace is the root object.  In V3, this maps 1:1 to a Postgres row
# in the `matters` table, with related tables for facts, authorities, and drafts.
#
# Today's equivalent is spread across:
#   LexState["matter_id"], ["matter_type"], ["parties"] — intake
#   LexState["research_findings"] — unstructured string
#   LexState["draft_output"] — unstructured string
#   ~/.lexagent/matters/{id}/MEMORY.md — unstructured markdown
#
# WHY centralise?  SQL queries:
#   SELECT * FROM facts WHERE matter_id = $1 AND status = 'disputed'
#   SELECT * FROM authorities WHERE matter_id = $1 AND verified = false
#   SELECT * FROM drafts WHERE matter_id = $1 ORDER BY version DESC LIMIT 1
# These queries drive the morning brief, risk report, and citation audit.

class MatterWorkspace(BaseModel):
    matter_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    firm_id: str
    matter_type: str                   # "writ_petition" | "legal_notice" | "ni_act_138" etc.
    title: str                         # human-readable title for the matter
    jurisdiction: str                  # "Delhi HC" | "Supreme Court" | "Tis Hazari MM Court"
    filing_date: Optional[date] = None # target filing date (drives deadline alerts)
    status: Literal[
        "intake", "research", "drafting", "review", "filed", "closed"
    ] = "intake"
    facts: list[Fact] = []
    authorities: list[Authority] = []
    drafts: list[Draft] = []
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def unverified_authorities(self) -> list[Authority]:
        """All authorities not yet confirmed against Indian Kanoon."""
        return [a for a in self.authorities if not a.verified]

    def disputed_facts(self) -> list[Fact]:
        """Facts the opposing party contests — these need evidence."""
        return [f for f in self.facts if f.status == "disputed"]

    def latest_draft(self) -> Optional[Draft]:
        """The most recent version of any draft document."""
        if not self.drafts:
            return None
        return max(self.drafts, key=lambda d: d.version)

    def risk_summary(self) -> dict:
        """
        Quick risk snapshot surfaced in the morning brief.
        In V3, this feeds the daily digest sent to the lawyer.
        """
        return {
            "unverified_citations": len(self.unverified_authorities()),
            "disputed_facts": len(self.disputed_facts()),
            "latest_draft_status": (
                self.latest_draft().status if self.latest_draft() else "none"
            ),
            "matter_status": self.status,
        }


# ── SECTION 7: LIVE DEMO ─────────────────────────────────────────────────────
#
# We create a realistic matter workspace for an NI Act 138 case,
# add two Facts (one from a document, one from the agent),
# add one Authority (unverified — agent suggested it),
# add one Draft, and then run all the safety checks.

def run_demo() -> None:
    print("=" * 60)
    print("DEMO: NI Act 138 — Cheque Dishonour Matter")
    print("=" * 60)

    # ── 7A: Create the matter workspace ──
    matter = MatterWorkspace(
        firm_id="firm_alpha",
        matter_type="ni_act_138",
        title="M/s Sunrise Traders v. Ravi Kumar — Cheque Dishonour",
        jurisdiction="Metropolitan Magistrate Court, Saket, Delhi",
        filing_date=date(2026, 6, 15),
    )
    print(f"\n[MATTER CREATED]")
    print(f"  matter_id  : {matter.matter_id}")
    print(f"  type       : {matter.matter_type}")
    print(f"  jurisdiction: {matter.jurisdiction}")
    print(f"  filing date : {matter.filing_date}")

    # ── 7B: Add a fact extracted from an uploaded document ──
    # Source: the bank's dishonour memo (a scanned PDF).
    # confidence=0.92 because OCR read the date clearly.
    cheque_date_fact = Fact(
        matter_id=matter.matter_id,
        text="Cheque No. 004521 drawn on HDFC Bank, Lajpat Nagar, dated 01-Feb-2026, "
             "for Rs. 5,00,000/-, was dishonoured on 05-Feb-2026 with memo "
             "'funds insufficient'.",
        status="alleged",  # still alleged — not yet admitted by the accused
        provenance=[
            Provenance(
                source_type="document",
                source_id="upload_bank_memo_001",
                quote="Cheque No. 004521 ... Reason: Funds Insufficient",
                confidence=0.92,
            )
        ],
    )
    matter.facts.append(cheque_date_fact)
    print(f"\n[FACT 1 — from document]")
    print(f"  text   : {cheque_date_fact.text[:70]}...")
    print(f"  status : {cheque_date_fact.status}")
    print(f"  source : {cheque_date_fact.provenance[0].source_type} "
          f"(confidence={cheque_date_fact.provenance[0].confidence})")
    print(f"  safe to plead? {cheque_date_fact.is_safe_to_plead()}")

    # ── 7C: Add a fact generated by the agent ──
    # The agent inferred the limitation period from the dates above.
    # confidence=0.85 because it is a legal inference, not a document quote.
    limitation_fact = Fact(
        matter_id=matter.matter_id,
        text="Legal notice dated 20-Feb-2026 was served within 30 days of dishonour "
             "(05-Feb-2026), satisfying Section 138 proviso (b).",
        status="alleged",
        provenance=[
            Provenance(
                source_type="agent",
                source_id="session_abc123",
                quote=None,
                confidence=0.85,
            )
        ],
    )
    matter.facts.append(limitation_fact)
    print(f"\n[FACT 2 — from agent inference]")
    print(f"  text   : {limitation_fact.text[:70]}...")
    print(f"  status : {limitation_fact.status}")
    print(f"  source : {limitation_fact.provenance[0].source_type} "
          f"(confidence={limitation_fact.provenance[0].confidence})")
    print(f"  safe to plead? {limitation_fact.is_safe_to_plead()}")

    # ── 7D: Add an authority suggested by the agent (not yet verified) ──
    # verified=False because we have not confirmed this on Indian Kanoon yet.
    authority = Authority(
        type="case",
        title="Dashrath Rupsingh Rathod v. State of Maharashtra",
        citation="(2014) 9 SCC 129",
        proposition="Territorial jurisdiction for Section 138 NI Act lies where the "
                    "cheque was dishonoured (bank branch location), not where payee "
                    "presented or deposited the cheque.",
        treatment="binding",
        verified=False,  # CRITICAL: agent suggested this; not yet confirmed
    )
    matter.authorities.append(authority)
    print(f"\n[AUTHORITY — agent-suggested, UNVERIFIED]")
    print(f"  title    : {authority.title}")
    print(f"  citation : {authority.citation}")
    print(f"  treatment: {authority.treatment}")
    print(f"  verified : {authority.verified}")
    print(f"  safe to cite? {authority.is_safe_to_cite()}")
    print(f"  *** This authority MUST NOT appear in any filed document yet. ***")

    # ── 7E: Add the first draft ──
    draft = Draft(
        matter_id=matter.matter_id,
        doc_type="section_138_complaint",
        version=1,
        content=(
            "IN THE COURT OF THE LEARNED METROPOLITAN MAGISTRATE...\n"
            "[COMPLAINT UNDER SECTION 138 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881]\n"
            "... [agent-generated content] ..."
        ),
        status="draft",
    )
    matter.drafts.append(draft)
    print(f"\n[DRAFT v{draft.version}]")
    print(f"  doc_type    : {draft.doc_type}")
    print(f"  status      : {draft.status}")
    print(f"  can be edited? {draft.can_be_edited()}")

    # ── 7F: Risk summary ──
    print(f"\n[RISK SUMMARY]")
    risk = matter.risk_summary()
    for k, v in risk.items():
        print(f"  {k}: {v}")

    # ── 7G: Pydantic catching a bad status value ──
    print(f"\n[PYDANTIC VALIDATION — catching a bad status value]")
    try:
        bad_fact = Fact(
            matter_id=matter.matter_id,
            text="This will fail.",
            status="definitely_true",  # not in the Literal — Pydantic will reject this
            provenance=[Provenance(source_type="user")],
        )
    except ValidationError as e:
        print(f"  ValidationError caught (as expected):")
        for err in e.errors():
            print(f"    field={err['loc']}  msg={err['msg']}")
        print(f"  WHY this matters: the agent cannot accidentally mark a fact as")
        print(f"  'definitely_true' — only the four allowed statuses are valid.")

    # ── 7H: Pydantic catching an unverified authority being cited ──
    print(f"\n[SAFETY CHECK — unverified authorities]")
    unverified = matter.unverified_authorities()
    print(f"  Unverified authorities: {len(unverified)}")
    for a in unverified:
        print(f"    - {a.title} ({a.citation})")
    print(f"  A pre-filing check would block submission until this list is empty.")

    print(f"\n{'=' * 60}")
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/state.py.  Find the fields that hold research findings,
#    statutes cited, and limitation analysis.  Which of these would map to
#    Fact records?  Which would map to Authority records?  Are any lost entirely
#    in the translation to a structured workspace?
#
# 2. The Fact model defaults status to "alleged".  In what scenario would a
#    lawyer legitimately set status="admitted" before filing?
#    (Hint: look up "admission in pleadings" under Order VIII CPC.)
#
# 3. Authority.verified defaults to False.  Open lexagent/nodes/cite.py.
#    What does the cite node do today to verify a citation?
#    What would it need to do differently to set verified=True on an Authority
#    record in the MatterWorkspace?
#
# 4. MatterWorkspace.risk_summary() returns a dict.  Extend it: add a field
#    "overruled_authorities" that counts authorities with treatment="overruled".
#    Then write a rule: if overruled_authorities > 0, matter_status should
#    never be "filed".  Where in the system would you enforce this rule?
#
# 5. Read LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md Section 6.
#    What Postgres schema does it propose for the facts and authorities tables?
#    Does it use a separate table per entity type, or a single JSONB column
#    on the matters table?  What are the tradeoffs of each approach?
