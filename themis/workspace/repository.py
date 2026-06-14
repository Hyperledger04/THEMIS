"""
PostgresWorkspaceRepository — typed CRUD for all Matter Workspace objects.

Isolation rule (§11A Failure Mode 3 — Confidentiality Bleed):
Every query touching legal objects MUST include both firm_id AND matter_id
predicates. Tables without a direct firm_id column use a subquery against
matters to enforce the tenant boundary. No full-table scans without scope.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional

from themis.workspace.models import (
    Authority,
    ChronologyItem,
    Deadline,
    DocumentRecord,
    Draft,
    EvidenceItem,
    ExtractedFact,
    FeedbackItem,
    Issue,
    Matter,
    Party,
    PlaybookNote,
    ResearchMemo,
    RiskAnalysis,
    SourceAnchor,
    StylePreference,
    Task,
)

# Subquery used by tables that have matter_id but no direct firm_id column.
# Enforces tenant isolation via the matters table.
_FIRM_SCOPE = "matter_id IN (SELECT matter_id FROM matters WHERE firm_id = %s)"


class PostgresWorkspaceRepository:
    """Postgres CRUD for all Matter Workspace tables."""

    def __init__(self, postgres_url: str) -> None:
        self._postgres_url = postgres_url

    @contextmanager
    def _connect(self) -> Generator:
        import psycopg
        with psycopg.connect(self._postgres_url) as conn:
            yield conn

    # ------------------------------------------------------------------
    # Matter
    # ------------------------------------------------------------------

    def create_matter(self, matter: Matter) -> Matter:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO matters
                    (matter_id, firm_id, user_id, title, matter_type,
                     jurisdiction, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    matter.matter_id, matter.firm_id, matter.user_id,
                    matter.title, matter.matter_type, matter.jurisdiction,
                    matter.status, matter.created_at, matter.updated_at,
                ),
            )
            conn.commit()
        return matter

    def get_matter(self, matter_id: str, firm_id: str) -> Optional[Matter]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT matter_id, firm_id, user_id, title, matter_type, "
                "jurisdiction, status, created_at, updated_at "
                "FROM matters WHERE matter_id = %s AND firm_id = %s",
                (matter_id, firm_id),
            ).fetchone()
        if not row:
            return None
        return Matter(
            matter_id=row[0], firm_id=row[1], user_id=row[2],
            title=row[3], matter_type=row[4], jurisdiction=row[5],
            status=row[6], created_at=str(row[7]), updated_at=str(row[8]),
        )

    def list_matters(self, firm_id: str, status: Optional[str] = None) -> list[Matter]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT matter_id, firm_id, user_id, title, matter_type, "
                    "jurisdiction, status, created_at, updated_at "
                    "FROM matters WHERE firm_id = %s AND status = %s "
                    "ORDER BY updated_at DESC",
                    (firm_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT matter_id, firm_id, user_id, title, matter_type, "
                    "jurisdiction, status, created_at, updated_at "
                    "FROM matters WHERE firm_id = %s ORDER BY updated_at DESC",
                    (firm_id,),
                ).fetchall()
        return [
            Matter(
                matter_id=r[0], firm_id=r[1], user_id=r[2],
                title=r[3], matter_type=r[4], jurisdiction=r[5],
                status=r[6], created_at=str(r[7]), updated_at=str(r[8]),
            )
            for r in rows
        ]

    def update_matter_status(self, matter_id: str, firm_id: str, status: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE matters SET status = %s, updated_at = %s "
                "WHERE matter_id = %s AND firm_id = %s",
                (status, now, matter_id, firm_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # DocumentRecord  (has its own firm_id column)
    # ------------------------------------------------------------------

    def create_document(self, doc: DocumentRecord) -> DocumentRecord:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents
                    (document_id, matter_id, firm_id, filename, mime_type,
                     storage_uri, parser, page_count, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doc.document_id, doc.matter_id, doc.firm_id, doc.filename,
                    doc.mime_type, doc.storage_uri, doc.parser, doc.page_count,
                    doc.status, doc.created_at,
                ),
            )
            conn.commit()
        return doc

    def get_document(self, document_id: str, matter_id: str, firm_id: str) -> Optional[DocumentRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT document_id, matter_id, firm_id, filename, mime_type, "
                "storage_uri, parser, page_count, status, created_at "
                "FROM documents "
                "WHERE document_id = %s AND matter_id = %s AND firm_id = %s",
                (document_id, matter_id, firm_id),
            ).fetchone()
        if not row:
            return None
        return DocumentRecord(
            document_id=row[0], matter_id=row[1], firm_id=row[2],
            filename=row[3], mime_type=row[4], storage_uri=row[5],
            parser=row[6], page_count=row[7], status=row[8],
            created_at=str(row[9]),
        )

    def list_documents(self, matter_id: str, firm_id: str) -> list[DocumentRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT document_id, matter_id, firm_id, filename, mime_type, "
                "storage_uri, parser, page_count, status, created_at "
                "FROM documents WHERE matter_id = %s AND firm_id = %s "
                "ORDER BY created_at DESC",
                (matter_id, firm_id),
            ).fetchall()
        return [
            DocumentRecord(
                document_id=r[0], matter_id=r[1], firm_id=r[2],
                filename=r[3], mime_type=r[4], storage_uri=r[5],
                parser=r[6], page_count=r[7], status=r[8],
                created_at=str(r[9]),
            )
            for r in rows
        ]

    def update_document_status(
        self,
        document_id: str,
        matter_id: str,
        firm_id: str,
        status: str,
        page_count: Optional[int] = None,
        parser: Optional[str] = None,
    ) -> None:
        with self._connect() as conn:
            if page_count is not None and parser is not None:
                conn.execute(
                    "UPDATE documents SET status = %s, page_count = %s, parser = %s "
                    "WHERE document_id = %s AND matter_id = %s AND firm_id = %s",
                    (status, page_count, parser, document_id, matter_id, firm_id),
                )
            else:
                conn.execute(
                    "UPDATE documents SET status = %s "
                    "WHERE document_id = %s AND matter_id = %s AND firm_id = %s",
                    (status, document_id, matter_id, firm_id),
                )
            conn.commit()

    # ------------------------------------------------------------------
    # SourceAnchor  (scoped via matter_id + JOIN to documents for firm check)
    # ------------------------------------------------------------------

    def create_anchor(self, anchor: SourceAnchor) -> SourceAnchor:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_anchors
                    (anchor_id, matter_id, document_id, page, line_start, line_end,
                     excerpt, confidence, extractor_agent, extraction_run_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    anchor.anchor_id, anchor.matter_id, anchor.document_id,
                    anchor.page, anchor.line_start, anchor.line_end,
                    anchor.excerpt, anchor.confidence, anchor.extractor_agent,
                    anchor.extraction_run_id, anchor.created_at,
                ),
            )
            conn.commit()
        return anchor

    def bulk_create_anchors(self, anchors: list[SourceAnchor]) -> None:
        if not anchors:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO source_anchors
                    (anchor_id, matter_id, document_id, page, line_start, line_end,
                     excerpt, confidence, extractor_agent, extraction_run_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        a.anchor_id, a.matter_id, a.document_id,
                        a.page, a.line_start, a.line_end,
                        a.excerpt, a.confidence, a.extractor_agent,
                        a.extraction_run_id, a.created_at,
                    )
                    for a in anchors
                ],
            )
            conn.commit()

    def get_anchors_for_document(
        self, document_id: str, matter_id: str, firm_id: str
    ) -> list[SourceAnchor]:
        # firm_id enforced via JOIN to documents which has its own firm_id column
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sa.anchor_id, sa.matter_id, sa.document_id, sa.page,
                       sa.line_start, sa.line_end, sa.excerpt, sa.confidence,
                       sa.extractor_agent, sa.extraction_run_id, sa.created_at
                FROM source_anchors sa
                JOIN documents d ON d.document_id = sa.document_id
                WHERE sa.document_id = %s AND sa.matter_id = %s AND d.firm_id = %s
                ORDER BY sa.page, sa.line_start
                """,
                (document_id, matter_id, firm_id),
            ).fetchall()
        return [
            SourceAnchor(
                anchor_id=r[0], matter_id=r[1], document_id=r[2],
                page=r[3], line_start=r[4], line_end=r[5],
                excerpt=r[6], confidence=float(r[7]),
                extractor_agent=r[8], extraction_run_id=r[9],
                created_at=str(r[10]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # ExtractedFact  (scoped via matter_id + subquery for firm_id)
    # ------------------------------------------------------------------

    def create_fact(self, fact: ExtractedFact) -> ExtractedFact:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO extracted_facts
                    (fact_id, matter_id, text, status, confidence,
                     source_anchor_ids, extractor_agent, extraction_run_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                (
                    fact.fact_id, fact.matter_id, fact.text, fact.status,
                    fact.confidence, json.dumps(fact.source_anchor_ids),
                    fact.extractor_agent, fact.extraction_run_id, fact.created_at,
                ),
            )
            conn.commit()
        return fact

    def bulk_create_facts(self, facts: list[ExtractedFact]) -> None:
        if not facts:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO extracted_facts
                    (fact_id, matter_id, text, status, confidence,
                     source_anchor_ids, extractor_agent, extraction_run_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                [
                    (
                        f.fact_id, f.matter_id, f.text, f.status,
                        f.confidence, json.dumps(f.source_anchor_ids),
                        f.extractor_agent, f.extraction_run_id, f.created_at,
                    )
                    for f in facts
                ],
            )
            conn.commit()

    def list_facts(
        self, matter_id: str, firm_id: str, status: Optional[str] = None
    ) -> list[ExtractedFact]:
        with self._connect() as conn:
            base = (
                "SELECT fact_id, matter_id, text, status, confidence, "
                f"source_anchor_ids, extractor_agent, extraction_run_id, created_at "
                f"FROM extracted_facts "
                f"WHERE matter_id = %s AND {_FIRM_SCOPE}"
            )
            params: tuple = (matter_id, firm_id)
            if status:
                base += " AND status = %s"
                params = (matter_id, firm_id, status)
            rows = conn.execute(base + " ORDER BY created_at ASC", params).fetchall()
        return [
            ExtractedFact(
                fact_id=r[0], matter_id=r[1], text=r[2], status=r[3],
                confidence=float(r[4]),
                source_anchor_ids=r[5] if isinstance(r[5], list) else json.loads(r[5] or "[]"),
                extractor_agent=r[6], extraction_run_id=r[7],
                created_at=str(r[8]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # ChronologyItem
    # ------------------------------------------------------------------

    def create_chronology_item(self, item: ChronologyItem) -> ChronologyItem:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chronology_items
                    (chronology_id, matter_id, date_text, event, normalized_date,
                     confidence, source_anchor_ids, extractor_agent,
                     extraction_run_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                (
                    item.chronology_id, item.matter_id, item.date_text, item.event,
                    item.normalized_date, item.confidence,
                    json.dumps(item.source_anchor_ids),
                    item.extractor_agent, item.extraction_run_id, item.created_at,
                ),
            )
            conn.commit()
        return item

    def bulk_create_chronology(self, items: list[ChronologyItem]) -> None:
        if not items:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO chronology_items
                    (chronology_id, matter_id, date_text, event, normalized_date,
                     confidence, source_anchor_ids, extractor_agent,
                     extraction_run_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                [
                    (
                        i.chronology_id, i.matter_id, i.date_text, i.event,
                        i.normalized_date, i.confidence,
                        json.dumps(i.source_anchor_ids),
                        i.extractor_agent, i.extraction_run_id, i.created_at,
                    )
                    for i in items
                ],
            )
            conn.commit()

    def list_chronology(self, matter_id: str, firm_id: str) -> list[ChronologyItem]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT chronology_id, matter_id, date_text, event, normalized_date, "
                f"confidence, source_anchor_ids, extractor_agent, extraction_run_id, created_at "
                f"FROM chronology_items "
                f"WHERE matter_id = %s AND {_FIRM_SCOPE} "
                f"ORDER BY normalized_date ASC NULLS LAST, created_at ASC",
                (matter_id, firm_id),
            ).fetchall()
        return [
            ChronologyItem(
                chronology_id=r[0], matter_id=r[1], date_text=r[2], event=r[3],
                normalized_date=str(r[4]) if r[4] else None,
                confidence=float(r[5]),
                source_anchor_ids=r[6] if isinstance(r[6], list) else json.loads(r[6] or "[]"),
                extractor_agent=r[7], extraction_run_id=r[8],
                created_at=str(r[9]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # EvidenceItem
    # ------------------------------------------------------------------

    def create_evidence_item(self, item: EvidenceItem) -> EvidenceItem:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evidence_items
                    (evidence_id, matter_id, title, description, document_id,
                     source_anchor_ids, confidence, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    item.evidence_id, item.matter_id, item.title, item.description,
                    item.document_id, json.dumps(item.source_anchor_ids),
                    item.confidence, item.created_at,
                ),
            )
            conn.commit()
        return item

    def list_evidence(self, matter_id: str, firm_id: str) -> list[EvidenceItem]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT evidence_id, matter_id, title, description, document_id, "
                f"source_anchor_ids, confidence, created_at "
                f"FROM evidence_items "
                f"WHERE matter_id = %s AND {_FIRM_SCOPE} "
                f"ORDER BY created_at ASC",
                (matter_id, firm_id),
            ).fetchall()
        return [
            EvidenceItem(
                evidence_id=r[0], matter_id=r[1], title=r[2], description=r[3],
                document_id=r[4],
                source_anchor_ids=r[5] if isinstance(r[5], list) else json.loads(r[5] or "[]"),
                confidence=float(r[6]), created_at=str(r[7]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Party
    # ------------------------------------------------------------------

    def create_party(self, party: Party) -> Party:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO parties
                    (party_id, matter_id, name, role, address, contact, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    party.party_id, party.matter_id, party.name, party.role,
                    party.address, party.contact, party.created_at,
                ),
            )
            conn.commit()
        return party

    def list_parties(self, matter_id: str, firm_id: str) -> list[Party]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT party_id, matter_id, name, role, address, contact, created_at "
                f"FROM parties WHERE matter_id = %s AND {_FIRM_SCOPE} "
                f"ORDER BY created_at ASC",
                (matter_id, firm_id),
            ).fetchall()
        return [
            Party(
                party_id=r[0], matter_id=r[1], name=r[2], role=r[3],
                address=r[4], contact=r[5], created_at=str(r[6]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Issue
    # ------------------------------------------------------------------

    def create_issue(self, issue: Issue) -> Issue:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO issues
                    (issue_id, matter_id, text, category, status,
                     source_anchor_ids, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    issue.issue_id, issue.matter_id, issue.text, issue.category,
                    issue.status, json.dumps(issue.source_anchor_ids), issue.created_at,
                ),
            )
            conn.commit()
        return issue

    def list_issues(self, matter_id: str, firm_id: str) -> list[Issue]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT issue_id, matter_id, text, category, status, "
                f"source_anchor_ids, created_at "
                f"FROM issues WHERE matter_id = %s AND {_FIRM_SCOPE} "
                f"ORDER BY created_at ASC",
                (matter_id, firm_id),
            ).fetchall()
        return [
            Issue(
                issue_id=r[0], matter_id=r[1], text=r[2], category=r[3],
                status=r[4],
                source_anchor_ids=r[5] if isinstance(r[5], list) else json.loads(r[5] or "[]"),
                created_at=str(r[6]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Authority
    # ------------------------------------------------------------------

    def create_authority(self, authority: Authority) -> Authority:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO authorities
                    (authority_id, matter_id, authority_type, title, citation,
                     court, url, proposition, treatment,
                     jurisdiction, country, court_tier, corpus_namespace,
                     verified_excerpt, paragraph_number, verification_status,
                     verified, source_anchor_ids, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    authority.authority_id, authority.matter_id,
                    authority.authority_type, authority.title, authority.citation,
                    authority.court, authority.url, authority.proposition,
                    authority.treatment,
                    authority.jurisdiction, authority.country,
                    authority.court_tier, authority.corpus_namespace,
                    authority.verified_excerpt, authority.paragraph_number,
                    authority.verification_status,
                    authority.verified,
                    json.dumps(authority.source_anchor_ids), authority.created_at,
                ),
            )
            conn.commit()
        return authority

    def update_authority_verification(
        self,
        authority_id: str,
        matter_id: str,
        firm_id: str,
        verification_status: str,
        verified_excerpt: Optional[str] = None,
        paragraph_number: Optional[str] = None,
    ) -> None:
        """Update citation verification result. Tri-state: verified/partial/contradicted."""
        verified = verification_status == "verified"
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE authorities
                SET verification_status = %s,
                    verified = %s,
                    verified_excerpt = %s,
                    paragraph_number = %s
                WHERE authority_id = %s AND matter_id = %s AND {_FIRM_SCOPE}
                """,
                (
                    verification_status, verified, verified_excerpt, paragraph_number,
                    authority_id, matter_id, firm_id,
                ),
            )
            conn.commit()

    def list_authorities(
        self,
        matter_id: str,
        firm_id: str,
        verified: Optional[bool] = None,
        verification_status: Optional[str] = None,
        corpus_namespace: Optional[str] = None,
    ) -> list[Authority]:
        with self._connect() as conn:
            base = (
                f"SELECT authority_id, matter_id, authority_type, title, citation, "
                f"court, url, proposition, treatment, "
                f"jurisdiction, country, court_tier, corpus_namespace, "
                f"verified_excerpt, paragraph_number, verification_status, "
                f"verified, source_anchor_ids, created_at "
                f"FROM authorities WHERE matter_id = %s AND {_FIRM_SCOPE}"
            )
            params: list = [matter_id, firm_id]
            if verified is not None:
                base += " AND verified = %s"
                params.append(verified)
            if verification_status is not None:
                base += " AND verification_status = %s"
                params.append(verification_status)
            if corpus_namespace is not None:
                base += " AND corpus_namespace = %s"
                params.append(corpus_namespace)
            rows = conn.execute(
                base + " ORDER BY court_tier ASC, created_at ASC", tuple(params)
            ).fetchall()
        return [
            Authority(
                authority_id=r[0], matter_id=r[1], authority_type=r[2],
                title=r[3], citation=r[4], court=r[5], url=r[6],
                proposition=r[7], treatment=r[8],
                jurisdiction=r[9], country=r[10],
                court_tier=r[11], corpus_namespace=r[12],
                verified_excerpt=r[13], paragraph_number=r[14],
                verification_status=r[15],
                verified=bool(r[16]),
                source_anchor_ids=r[17] if isinstance(r[17], list) else json.loads(r[17] or "[]"),
                created_at=str(r[18]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Draft  (immutable versions — create new version, never update content)
    # ------------------------------------------------------------------

    def create_draft(self, draft: Draft) -> Draft:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO drafts
                    (draft_id, matter_id, doc_type, version, content,
                     status, verification_report_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    draft.draft_id, draft.matter_id, draft.doc_type,
                    draft.version, draft.content, draft.status,
                    draft.verification_report_id, draft.created_at,
                ),
            )
            conn.commit()
        return draft

    def get_latest_draft(
        self, matter_id: str, firm_id: str, doc_type: str
    ) -> Optional[Draft]:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT draft_id, matter_id, doc_type, version, content, "
                f"status, verification_report_id, created_at "
                f"FROM drafts "
                f"WHERE matter_id = %s AND {_FIRM_SCOPE} AND doc_type = %s "
                f"ORDER BY version DESC LIMIT 1",
                (matter_id, firm_id, doc_type),
            ).fetchone()
        if not row:
            return None
        return Draft(
            draft_id=row[0], matter_id=row[1], doc_type=row[2],
            version=row[3], content=row[4], status=row[5],
            verification_report_id=row[6], created_at=str(row[7]),
        )

    def list_drafts(self, matter_id: str, firm_id: str) -> list[Draft]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT draft_id, matter_id, doc_type, version, content, "
                f"status, verification_report_id, created_at "
                f"FROM drafts WHERE matter_id = %s AND {_FIRM_SCOPE} "
                f"ORDER BY created_at DESC",
                (matter_id, firm_id),
            ).fetchall()
        return [
            Draft(
                draft_id=r[0], matter_id=r[1], doc_type=r[2],
                version=r[3], content=r[4], status=r[5],
                verification_report_id=r[6], created_at=str(r[7]),
            )
            for r in rows
        ]

    def update_draft_status(
        self, draft_id: str, matter_id: str, firm_id: str, status: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                f"UPDATE drafts SET status = %s "
                f"WHERE draft_id = %s AND matter_id = %s AND {_FIRM_SCOPE}",
                (status, draft_id, matter_id, firm_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Deadline
    # ------------------------------------------------------------------

    def create_deadline(self, deadline: Deadline) -> Deadline:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO deadlines
                    (deadline_id, matter_id, title, due_date, deadline_type,
                     status, source_anchor_ids, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    deadline.deadline_id, deadline.matter_id, deadline.title,
                    deadline.due_date, deadline.deadline_type, deadline.status,
                    json.dumps(deadline.source_anchor_ids), deadline.created_at,
                ),
            )
            conn.commit()
        return deadline

    def list_deadlines(
        self,
        matter_id: str,
        firm_id: str,
        status: Optional[str] = "upcoming",
    ) -> list[Deadline]:
        with self._connect() as conn:
            base = (
                f"SELECT deadline_id, matter_id, title, due_date, deadline_type, "
                f"status, source_anchor_ids, created_at "
                f"FROM deadlines WHERE matter_id = %s AND {_FIRM_SCOPE}"
            )
            params: tuple = (matter_id, firm_id)
            if status:
                base += " AND status = %s"
                params = (matter_id, firm_id, status)
            rows = conn.execute(base + " ORDER BY due_date ASC", params).fetchall()
        return [
            Deadline(
                deadline_id=r[0], matter_id=r[1], title=r[2],
                due_date=str(r[3]), deadline_type=r[4], status=r[5],
                source_anchor_ids=r[6] if isinstance(r[6], list) else json.loads(r[6] or "[]"),
                created_at=str(r[7]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Task
    # ------------------------------------------------------------------

    def create_task(self, task: Task) -> Task:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks
                    (task_id, matter_id, title, status, assigned_to, due_date, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    task.task_id, task.matter_id, task.title, task.status,
                    task.assigned_to, task.due_date, task.created_at,
                ),
            )
            conn.commit()
        return task

    def list_tasks(
        self, matter_id: str, firm_id: str, status: Optional[str] = None
    ) -> list[Task]:
        with self._connect() as conn:
            base = (
                f"SELECT task_id, matter_id, title, status, assigned_to, due_date, created_at "
                f"FROM tasks WHERE matter_id = %s AND {_FIRM_SCOPE}"
            )
            params: tuple = (matter_id, firm_id)
            if status:
                base += " AND status = %s"
                params = (matter_id, firm_id, status)
            rows = conn.execute(base + " ORDER BY due_date ASC NULLS LAST, created_at ASC", params).fetchall()
        return [
            Task(
                task_id=r[0], matter_id=r[1], title=r[2], status=r[3],
                assigned_to=r[4], due_date=str(r[5]) if r[5] else None,
                created_at=str(r[6]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # FeedbackItem
    # ------------------------------------------------------------------

    def create_feedback(self, item: FeedbackItem) -> FeedbackItem:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback_items
                    (feedback_id, matter_id, user_id, target_type, target_id,
                     signal, note, diff, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    item.feedback_id, item.matter_id, item.user_id,
                    item.target_type, item.target_id, item.signal,
                    item.note, item.diff, item.created_at,
                ),
            )
            conn.commit()
        return item

    def list_feedback(
        self,
        user_id: str,
        firm_id: str,
        matter_id: Optional[str] = None,
        target_type: Optional[str] = None,
        signal: Optional[str] = None,
        limit: int = 50,
    ) -> list[FeedbackItem]:
        with self._connect() as conn:
            base = (
                "SELECT feedback_id, matter_id, user_id, target_type, target_id, "
                "signal, note, diff, created_at FROM feedback_items "
                "WHERE user_id = %s"
            )
            params: list = [user_id]
            if matter_id is not None:
                base += " AND matter_id = %s"
                params.append(matter_id)
            if target_type is not None:
                base += " AND target_type = %s"
                params.append(target_type)
            if signal is not None:
                base += " AND signal = %s"
                params.append(signal)
            rows = conn.execute(
                base + " ORDER BY created_at DESC LIMIT %s",
                tuple(params) + (limit,),
            ).fetchall()
        return [
            FeedbackItem(
                feedback_id=r[0], matter_id=r[1], user_id=r[2],
                target_type=r[3], target_id=r[4], signal=r[5],
                note=r[6], diff=r[7], created_at=str(r[8]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # ResearchMemo  (Phase 5 — first-class workspace object)
    # ------------------------------------------------------------------

    def create_research_memo(self, memo: ResearchMemo) -> ResearchMemo:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO research_memos
                    (memo_id, matter_id, title, content, query,
                     authority_ids, source_anchor_ids, agent_run_id, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                """,
                (
                    memo.memo_id, memo.matter_id, memo.title, memo.content,
                    memo.query,
                    json.dumps(memo.authority_ids),
                    json.dumps(memo.source_anchor_ids),
                    memo.agent_run_id, memo.status, memo.created_at,
                ),
            )
            conn.commit()
        return memo

    def list_research_memos(
        self, matter_id: str, firm_id: str, status: Optional[str] = None
    ) -> list[ResearchMemo]:
        with self._connect() as conn:
            base = (
                f"SELECT memo_id, matter_id, title, content, query, "
                f"authority_ids, source_anchor_ids, agent_run_id, status, created_at "
                f"FROM research_memos WHERE matter_id = %s AND {_FIRM_SCOPE}"
            )
            params: list = [matter_id, firm_id]
            if status:
                base += " AND status = %s"
                params.append(status)
            rows = conn.execute(base + " ORDER BY created_at DESC", tuple(params)).fetchall()
        return [
            ResearchMemo(
                memo_id=r[0], matter_id=r[1], title=r[2], content=r[3], query=r[4],
                authority_ids=r[5] if isinstance(r[5], list) else json.loads(r[5] or "[]"),
                source_anchor_ids=r[6] if isinstance(r[6], list) else json.loads(r[6] or "[]"),
                agent_run_id=r[7], status=r[8], created_at=str(r[9]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # RiskAnalysis  (Phase 5)
    # ------------------------------------------------------------------

    def create_risk_analysis(self, analysis: RiskAnalysis) -> RiskAnalysis:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO risk_analyses
                    (risk_id, matter_id, draft_id, title, summary,
                     risks, agent_run_id, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                (
                    analysis.risk_id, analysis.matter_id, analysis.draft_id,
                    analysis.title, analysis.summary,
                    json.dumps(analysis.risks),
                    analysis.agent_run_id, analysis.status, analysis.created_at,
                ),
            )
            conn.commit()
        return analysis

    def list_risk_analyses(
        self, matter_id: str, firm_id: str, draft_id: Optional[str] = None
    ) -> list[RiskAnalysis]:
        with self._connect() as conn:
            base = (
                f"SELECT risk_id, matter_id, draft_id, title, summary, "
                f"risks, agent_run_id, status, created_at "
                f"FROM risk_analyses WHERE matter_id = %s AND {_FIRM_SCOPE}"
            )
            params: list = [matter_id, firm_id]
            if draft_id is not None:
                base += " AND draft_id = %s"
                params.append(draft_id)
            rows = conn.execute(base + " ORDER BY created_at DESC", tuple(params)).fetchall()
        return [
            RiskAnalysis(
                risk_id=r[0], matter_id=r[1], draft_id=r[2],
                title=r[3], summary=r[4],
                risks=r[5] if isinstance(r[5], list) else json.loads(r[5] or "[]"),
                agent_run_id=r[6], status=r[7], created_at=str(r[8]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # StylePreference  (Phase 6 — Learning Loop)
    # ------------------------------------------------------------------

    def upsert_style_preference(self, pref: StylePreference) -> StylePreference:
        """Insert or update a style preference (idempotent on preference_id)."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO style_preferences
                    (preference_id, user_id, firm_id, matter_type, doc_type,
                     preference_text, source_feedback_ids, active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (preference_id) DO UPDATE
                SET preference_text     = EXCLUDED.preference_text,
                    source_feedback_ids = EXCLUDED.source_feedback_ids,
                    active              = EXCLUDED.active,
                    updated_at          = EXCLUDED.updated_at
                """,
                (
                    pref.preference_id, pref.user_id, pref.firm_id,
                    pref.matter_type, pref.doc_type, pref.preference_text,
                    json.dumps(pref.source_feedback_ids), pref.active,
                    pref.created_at, pref.updated_at,
                ),
            )
            conn.commit()
        return pref

    def list_style_preferences(
        self,
        user_id: str,
        firm_id: str,
        matter_type: Optional[str] = None,
        doc_type: Optional[str] = None,
    ) -> list[StylePreference]:
        with self._connect() as conn:
            base = (
                "SELECT preference_id, user_id, firm_id, matter_type, doc_type, "
                "preference_text, source_feedback_ids, active, created_at, updated_at "
                "FROM style_preferences "
                "WHERE user_id = %s AND firm_id = %s AND active = TRUE"
            )
            params: list = [user_id, firm_id]
            if matter_type is not None:
                base += " AND (matter_type = %s OR matter_type IS NULL)"
                params.append(matter_type)
            if doc_type is not None:
                base += " AND (doc_type = %s OR doc_type IS NULL)"
                params.append(doc_type)
            rows = conn.execute(
                base + " ORDER BY updated_at DESC", tuple(params)
            ).fetchall()
        return [
            StylePreference(
                preference_id=r[0], user_id=r[1], firm_id=r[2],
                matter_type=r[3], doc_type=r[4], preference_text=r[5],
                source_feedback_ids=r[6] if isinstance(r[6], list) else json.loads(r[6] or "[]"),
                active=bool(r[7]), created_at=str(r[8]), updated_at=str(r[9]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # PlaybookNote  (Phase 6 — Learning Loop)
    # ------------------------------------------------------------------

    def create_playbook_note(self, note: PlaybookNote) -> PlaybookNote:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO playbook_notes
                    (note_id, firm_id, matter_type, jurisdiction, court,
                     observation, source_feedback_ids, active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    note.note_id, note.firm_id, note.matter_type,
                    note.jurisdiction, note.court, note.observation,
                    json.dumps(note.source_feedback_ids), note.active, note.created_at,
                ),
            )
            conn.commit()
        return note

    def list_playbook_notes(
        self,
        firm_id: str,
        matter_type: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        court: Optional[str] = None,
    ) -> list[PlaybookNote]:
        with self._connect() as conn:
            base = (
                "SELECT note_id, firm_id, matter_type, jurisdiction, court, "
                "observation, source_feedback_ids, active, created_at "
                "FROM playbook_notes WHERE firm_id = %s AND active = TRUE"
            )
            params: list = [firm_id]
            if matter_type is not None:
                base += " AND (matter_type = %s OR matter_type IS NULL)"
                params.append(matter_type)
            if jurisdiction is not None:
                base += " AND (jurisdiction = %s OR jurisdiction IS NULL)"
                params.append(jurisdiction)
            if court is not None:
                base += " AND (court = %s OR court IS NULL)"
                params.append(court)
            rows = conn.execute(
                base + " ORDER BY created_at DESC", tuple(params)
            ).fetchall()
        return [
            PlaybookNote(
                note_id=r[0], firm_id=r[1], matter_type=r[2],
                jurisdiction=r[3], court=r[4], observation=r[5],
                source_feedback_ids=r[6] if isinstance(r[6], list) else json.loads(r[6] or "[]"),
                active=bool(r[7]), created_at=str(r[8]),
            )
            for r in rows
        ]
