# Tests for the V3.4 ARQ worker (themis/worker/).
#
# Strategy: all tests are unit tests — no Redis, no Postgres, no live graph.
# We mock the external dependencies (LexConfig, MatterStore, get_graph) so
# the test suite passes in CI without any infrastructure running.

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# run_matter_job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_matter_job_skips_without_postgres():
    """run_matter_job returns a skip result when no postgres_url is configured."""
    from themis.worker.jobs import run_matter_job

    # WHY patch at source: imports in jobs.py are lazy (inside function bodies),
    # so patch("themis.worker.jobs.LexConfig") won't find them. Patch the module
    # where the symbol is actually defined instead.
    with patch("themis.config.LexConfig") as MockCfg:
        MockCfg.return_value.postgres_url = None
        result = await run_matter_job({}, "matter-123", "firm-abc")

    assert result["skipped"] is True
    assert result["reason"] == "no_postgres"
    assert result["matter_id"] == "matter-123"


@pytest.mark.asyncio
async def test_run_matter_job_matter_not_found():
    """run_matter_job returns an error dict when MatterStore cannot find the matter."""
    from themis.worker.jobs import run_matter_job

    mock_store = AsyncMock()
    mock_store.get_matter.return_value = None

    with patch("themis.config.LexConfig") as MockCfg, \
         patch("themis.db.matter_store.MatterStore", return_value=mock_store), \
         patch("themis.graph.get_graph"):
        MockCfg.return_value.postgres_url = "postgresql://localhost/test"
        result = await run_matter_job({}, "matter-999", "firm-abc")

    assert "error" in result
    assert result["matter_id"] == "matter-999"


@pytest.mark.asyncio
async def test_run_matter_job_resumes_paused_matter():
    """run_matter_job calls graph.ainvoke with next_action params for paused matters."""
    from themis.worker.jobs import run_matter_job

    matter = {
        "matter_id": "matter-001",
        "firm_id": "firm-abc",
        "status": "paused",
        "next_action": {"node": "draft", "params": {"matter_type": "ni_act_138"}},
    }
    mock_store = MagicMock()
    mock_store.get_matter = AsyncMock(return_value=matter)

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={"status": "complete", "matter_id": "matter-001"})

    with patch("themis.config.LexConfig") as MockCfg, \
         patch("themis.db.matter_store.MatterStore", return_value=mock_store), \
         patch("themis.graph.get_graph", return_value=mock_graph):
        MockCfg.return_value.postgres_url = "postgresql://localhost/test"
        result = await run_matter_job({}, "matter-001", "firm-abc")

    mock_graph.ainvoke.assert_called_once()
    call_args = mock_graph.ainvoke.call_args[0][0]
    assert call_args == {"matter_type": "ni_act_138"}
    assert result["status"] == "complete"


@pytest.mark.asyncio
async def test_run_matter_job_starts_fresh_for_non_paused():
    """run_matter_job builds an initial state for matters that are not paused."""
    from themis.worker.jobs import run_matter_job

    matter = {
        "matter_id": "matter-002",
        "firm_id": "firm-abc",
        "status": "complete",
        "matter_type": "bail",
        "jurisdiction": "Delhi",
        "parties": [],
        "purpose": "Get bail",
    }
    mock_store = MagicMock()
    mock_store.get_matter = AsyncMock(return_value=matter)

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={"status": "complete", "matter_id": "matter-002"})

    with patch("themis.config.LexConfig") as MockCfg, \
         patch("themis.db.matter_store.MatterStore", return_value=mock_store), \
         patch("themis.graph.get_graph", return_value=mock_graph):
        MockCfg.return_value.postgres_url = "postgresql://localhost/test"
        await run_matter_job({}, "matter-002", "firm-abc")

    call_args = mock_graph.ainvoke.call_args[0][0]
    assert call_args["matter_id"] == "matter-002"
    assert call_args["status"] == "researching"
    assert call_args["execution_plan"] == []


# ---------------------------------------------------------------------------
# index_matter_job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_matter_job_returns_stub_result():
    """index_matter_job is a V3.4 stub — must return indexed=False with reason."""
    from themis.worker.jobs import index_matter_job

    result = await index_matter_job({}, "matter-123")

    assert result["matter_id"] == "matter-123"
    assert result["indexed"] is False
    assert "stub" in result["reason"]


# ---------------------------------------------------------------------------
# recover_paused_matters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recover_paused_matters_skips_without_postgres():
    """recover_paused_matters skips gracefully when no postgres_url is configured."""
    from themis.worker.jobs import recover_paused_matters

    with patch("themis.config.LexConfig") as MockCfg:
        MockCfg.return_value.postgres_url = None
        result = await recover_paused_matters({})

    assert result["recovered"] == 0
    assert result["reason"] == "no_postgres"


@pytest.mark.asyncio
async def test_recover_paused_matters_enqueues_jobs():
    """recover_paused_matters enqueues run_matter_job for each paused matter."""
    from themis.worker.jobs import recover_paused_matters

    paused = [
        {"matter_id": "m-001", "firm_id": "firm-a"},
        {"matter_id": "m-002", "firm_id": "firm-b"},
    ]
    mock_store = MagicMock()
    mock_store.list_matters = AsyncMock(return_value=paused)

    mock_pool = AsyncMock()
    ctx = {"redis": mock_pool}

    with patch("themis.config.LexConfig") as MockCfg, \
         patch("themis.db.matter_store.MatterStore", return_value=mock_store):
        MockCfg.return_value.postgres_url = "postgresql://localhost/test"
        result = await recover_paused_matters(ctx)

    assert result["recovered"] == 2
    assert mock_pool.enqueue_job.call_count == 2
    first_call = mock_pool.enqueue_job.call_args_list[0]
    assert first_call[0][0] == "run_matter_job"
    assert first_call[0][1] == "m-001"


# ---------------------------------------------------------------------------
# _initial_state_from_matter
# ---------------------------------------------------------------------------


def test_initial_state_from_matter_required_fields():
    """_initial_state_from_matter produces a valid SeniorCounselState skeleton."""
    from themis.worker.jobs import _initial_state_from_matter

    matter = {
        "matter_id": "m-001",
        "firm_id": "firm-abc",
        "matter_type": "ni_act_138",
        "jurisdiction": "Delhi",
        "parties": [{"role": "complainant", "name": "Alice"}],
        "purpose": "Draft NI Act complaint",
    }
    state = _initial_state_from_matter(matter)

    assert state["matter_id"] == "m-001"
    assert state["firm_id"] == "firm-abc"
    assert state["matter_type"] == "ni_act_138"
    assert state["jurisdiction"] == "Delhi"
    assert state["status"] == "researching"
    assert state["execution_plan"] == []
    assert state["active_specialist"] is None
    assert state["messages"] == []


def test_initial_state_from_matter_handles_missing_fields():
    """_initial_state_from_matter uses safe defaults when matter fields are absent."""
    from themis.worker.jobs import _initial_state_from_matter

    state = _initial_state_from_matter({})

    assert state["matter_id"] == ""
    assert state["firm_id"] == "default"
    assert state["parties"] == []
    assert state["error"] is None


# ---------------------------------------------------------------------------
# WorkerSettings
# ---------------------------------------------------------------------------


def test_worker_settings_has_arq_required_attributes():
    """WorkerSettings exposes all attributes ARQ needs to start a worker."""
    # WHY: if arq is not installed this test is skipped, not failed
    pytest.importorskip("arq")

    from themis.worker.main import WorkerSettings

    assert hasattr(WorkerSettings, "functions")
    assert hasattr(WorkerSettings, "on_startup")
    assert hasattr(WorkerSettings, "redis_settings")
    assert hasattr(WorkerSettings, "max_jobs")
    assert hasattr(WorkerSettings, "job_timeout")
    assert len(WorkerSettings.functions) == 3


def test_worker_settings_functions_are_callable():
    """All registered job functions are importable async callables."""
    pytest.importorskip("arq")

    import asyncio
    from themis.worker.main import WorkerSettings

    for fn in WorkerSettings.functions:
        assert callable(fn)
        assert asyncio.iscoroutinefunction(fn), f"{fn.__name__} must be async"
