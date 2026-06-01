"""Tests for Matter Workspace Pydantic models — lexagent/workspace/models.py."""
import pytest
from lexagent.workspace.models import (
    Authority,
    ChronologyItem,
    Deadline,
    Draft,
    EvidenceItem,
    ExtractedFact,
    FeedbackItem,
    Issue,
    Matter,
    DocumentRecord,
    Party,
    SourceAnchor,
    Task,
)


class TestMatter:
    def test_defaults(self):
        m = Matter(title="NI Act 138 Complaint", matter_type="criminal")
        assert m.matter_id.startswith("matter_")
        assert m.status == "active"
        assert m.firm_id == "default"

    def test_custom_fields(self):
        m = Matter(title="Writ", matter_type="constitutional", jurisdiction="Supreme Court of India")
        assert m.jurisdiction == "Supreme Court of India"

    def test_id_uniqueness(self):
        ids = {Matter(title=f"M{i}", matter_type="t").matter_id for i in range(50)}
        assert len(ids) == 50


class TestDocumentRecord:
    def test_defaults(self):
        d = DocumentRecord(matter_id="m_001", filename="order.pdf", storage_uri="s3://bucket/order.pdf")
        assert d.document_id.startswith("doc_")
        assert d.status == "uploaded"

    def test_mime_type_optional(self):
        d = DocumentRecord(matter_id="m_001", filename="f.pdf", storage_uri="s3://x")
        assert d.mime_type is None


class TestSourceAnchor:
    def test_viewer_url_format(self):
        a = SourceAnchor(
            matter_id="matter_001",
            document_id="doc_001",
            page=4,
            line_start=27,
            excerpt="Cheque was dishonoured.",
        )
        url = a.viewer_url()
        assert "/document-viewer/matter_001/doc_001" in url
        assert "page=4" in url
        assert "line=27" in url
        assert f"anchor={a.anchor_id}" in url

    def test_footnote_format(self):
        a = SourceAnchor(matter_id="m", document_id="d", excerpt="x")
        assert a.footnote() == f"[{a.anchor_id}]"

    def test_viewer_url_without_page(self):
        a = SourceAnchor(matter_id="m", document_id="d", excerpt="x")
        url = a.viewer_url()
        assert "page=" in url  # key present even if empty


class TestExtractedFact:
    def test_footnoted_text_with_anchors(self):
        f = ExtractedFact(
            matter_id="m",
            text="Cheque dishonoured on 14 March 2026.",
            source_anchor_ids=["anchor_abc", "anchor_def"],
        )
        ft = f.footnoted_text()
        assert "anchor_abc" in ft
        assert "anchor_def" in ft

    def test_footnoted_text_no_anchors(self):
        f = ExtractedFact(matter_id="m", text="Some fact.")
        assert f.footnoted_text() == "Some fact."

    def test_needs_source_status(self):
        f = ExtractedFact(matter_id="m", text="x", status="needs_source")
        assert f.status == "needs_source"


class TestChronologyItem:
    def test_defaults(self):
        c = ChronologyItem(matter_id="m", date_text="14 March 2026", event="Cheque dishonoured")
        assert c.chronology_id.startswith("chrono_")
        assert c.confidence == 0.0

    def test_source_anchor_ids_list(self):
        c = ChronologyItem(
            matter_id="m", date_text="d", event="e",
            source_anchor_ids=["a1", "a2"],
        )
        assert len(c.source_anchor_ids) == 2


class TestParty:
    def test_defaults(self):
        p = Party(matter_id="m", name="Rahul Sharma")
        assert p.party_id.startswith("party_")
        assert p.role == "other"

    def test_roles(self):
        for role in ("complainant", "respondent", "applicant", "opponent", "witness", "other"):
            p = Party(matter_id="m", name="X", role=role)
            assert p.role == role


class TestIssue:
    def test_defaults(self):
        i = Issue(matter_id="m", text="Whether limitation has expired?")
        assert i.issue_id.startswith("issue_")
        assert i.status == "open"


class TestAuthority:
    def test_defaults(self):
        a = Authority(
            matter_id="m",
            title="Dashrath Rupsingh Rathod v. State of Maharashtra",
            proposition="Complaint must be filed where cheque was dishonoured.",
        )
        assert a.authority_id.startswith("auth_")
        assert not a.verified
        assert a.treatment == "unknown"

    def test_binding_treatment(self):
        a = Authority(
            matter_id="m", title="T", proposition="P",
            treatment="binding", court="Supreme Court of India",
        )
        assert a.treatment == "binding"


class TestDraft:
    def test_defaults(self):
        d = Draft(matter_id="m", doc_type="legal_notice", content="Without prejudice...")
        assert d.draft_id.startswith("draft_")
        assert d.version == 1
        assert d.status == "draft"

    def test_version_increment(self):
        d1 = Draft(matter_id="m", doc_type="t", content="v1")
        d2 = Draft(matter_id="m", doc_type="t", content="v2", version=2)
        assert d2.version == 2


class TestFeedbackItem:
    def test_accepted_signal(self):
        f = FeedbackItem(user_id="u1", target_type="draft", signal="accepted")
        assert f.feedback_id.startswith("feedback_")
        assert f.signal == "accepted"

    def test_all_signals(self):
        for sig in ("accepted", "rejected", "edited", "preferred", "corrected"):
            f = FeedbackItem(user_id="u", target_type="draft", signal=sig)
            assert f.signal == sig


class TestDeadline:
    def test_defaults(self):
        d = Deadline(matter_id="m", title="Limitation period", due_date="2026-06-14")
        assert d.deadline_id.startswith("deadline_")
        assert d.status == "upcoming"


class TestTask:
    def test_defaults(self):
        t = Task(matter_id="m", title="Draft legal notice")
        assert t.task_id.startswith("task_")
        assert t.status == "pending"
