from themis.ingestion.anchors import build_line_anchors
from themis.runtime.models import AgentApproval, AgentJob, AgentRun, AgentStep
from themis.runtime.postgres import RUNTIME_SCHEMA_SQL
from themis.workspace.models import ExtractedFact, SourceAnchor


def test_source_anchor_builds_clickable_viewer_url():
    anchor = SourceAnchor(
        anchor_id="F3",
        matter_id="M-001",
        document_id="doc_001",
        page=4,
        line_start=27,
        line_end=29,
        excerpt="Cheque bearing no. 123456 was returned unpaid.",
    )

    assert anchor.viewer_url() == "/document-viewer/M-001/doc_001?page=4&line=27&anchor=F3"
    assert anchor.footnote() == "[F3]"


def test_extracted_fact_renders_footnoted_text():
    fact = ExtractedFact(
        matter_id="M-001",
        text="The cheque was dishonoured on 14 March 2026.",
        source_anchor_ids=["F3", "F4"],
    )

    assert fact.footnoted_text() == "The cheque was dishonoured on 14 March 2026. [F3][F4]"


def test_build_line_anchors_skips_blank_lines_and_preserves_line_numbers():
    anchors = build_line_anchors(
        matter_id="M-001",
        document_id="doc_001",
        page=2,
        text="First line\n\nThird line",
        extraction_run_id="run_1",
    )

    assert len(anchors) == 2
    assert anchors[0].line_start == 1
    assert anchors[0].excerpt == "First line"
    assert anchors[1].line_start == 3
    assert anchors[1].viewer_url().endswith("page=2&line=3&anchor=" + anchors[1].anchor_id)


def test_runtime_models_match_public_job_shape():
    run = AgentRun(matter_id="M-001", goal="Build NI Act chronology")
    job = AgentJob(
        matter_id="M-001",
        run_id=run.run_id,
        type="build_chronology",
        agent="chronology_agent",
    )
    step = AgentStep(job_id=job.job_id, run_id=run.run_id, name="extract_dates")
    approval = AgentApproval(
        matter_id="M-001",
        run_id=run.run_id,
        requested_action="send_legal_notice",
        risk_level="high",
    )

    assert job.status == "queued"
    assert job.requires_approval is False
    assert step.status == "queued"
    assert approval.status == "pending"


def test_runtime_schema_contains_core_tables():
    for table in [
        "agent_runs",
        "agent_jobs",
        "agent_steps",
        "agent_tool_calls",
        "agent_artifacts",
        "agent_approvals",
        "agent_notifications",
        "source_anchors",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in RUNTIME_SCHEMA_SQL
