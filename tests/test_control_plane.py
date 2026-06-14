# tests/test_control_plane.py — Tests for the FastAPI control plane REST and WebSocket endpoints.
#
# All LangGraph calls are monkeypatched out so tests run fully offline.

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_graph_mock(draft="Test draft", error=None):
    """Return a mock graph whose ainvoke returns a realistic final state."""
    final_state = {
        "draft_output": draft,
        "plain_english_summary": "Summary.",
        "contract_review_output": None,
        "error": error,
        "intake_complete": True,
    }
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value=final_state)
    graph.aget_state = AsyncMock(return_value=None)  # new matter by default
    graph.astream_events = AsyncMock(return_value=_async_iter([]))
    return graph


async def _async_iter(items):
    for item in items:
        yield item


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from themis.gateway.control_plane import app
    return TestClient(app)


# ─── Health ──────────────────────────────────────────────────────────────────

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_document_viewer_returns_anchor_target(client):
    with patch("themis.gateway.control_plane.LexConfig") as cfg_cls:
        cfg = MagicMock()
        cfg.api_secret_key = None
        cfg.default_firm_id = "default"
        cfg_cls.return_value = cfg

        resp = client.get("/document-viewer/M-001/doc_001?page=4&line=27&anchor=F3")

    assert resp.status_code == 200
    data = resp.json()
    assert data["matter_id"] == "M-001"
    assert data["document_id"] == "doc_001"
    assert data["page"] == 4
    assert data["line"] == 27
    assert data["anchor"] == "F3"


# ─── Auth ────────────────────────────────────────────────────────────────────

def test_send_message_no_auth_required_when_key_not_set(client):
    """In single-lawyer mode (no api_secret_key) auth is skipped."""
    graph = _make_graph_mock()
    with (
        patch("themis.gateway.control_plane.get_graph", return_value=graph),
        patch("themis.gateway.control_plane.LexConfig") as cfg_cls,
    ):
        cfg = MagicMock()
        cfg.api_secret_key = None
        cfg.default_firm_id = "default"
        cfg_cls.return_value = cfg

        resp = client.post(
            "/api/v1/matters/M-test/message",
            json={"text": "I need to draft an injunction."},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["matter_id"] == "M-test"


def test_send_message_rejects_missing_token(client):
    """When api_secret_key is set, missing Bearer token → 401."""
    with patch("themis.gateway.control_plane.LexConfig") as cfg_cls:
        cfg = MagicMock()
        cfg.api_secret_key = "secret-key"
        cfg.default_firm_id = "firm1"
        cfg_cls.return_value = cfg

        resp = client.post(
            "/api/v1/matters/M-test/message",
            json={"text": "brief"},
        )
    assert resp.status_code == 401


def test_send_message_rejects_wrong_token(client):
    """Wrong Bearer token → 403."""
    with patch("themis.gateway.control_plane.LexConfig") as cfg_cls:
        cfg = MagicMock()
        cfg.api_secret_key = "secret-key"
        cfg.default_firm_id = "firm1"
        cfg_cls.return_value = cfg

        resp = client.post(
            "/api/v1/matters/M-test/message",
            headers={"Authorization": "Bearer wrong"},
            json={"text": "brief"},
        )
    assert resp.status_code == 403


# ─── send_message behaviour ───────────────────────────────────────────────────

def test_send_message_new_matter_resets_intake(client):
    """New matter (no checkpoint): intake_complete=False is sent to the graph."""
    graph = _make_graph_mock()
    # aget_state returns None → new matter
    graph.aget_state = AsyncMock(return_value=None)

    captured = {}

    async def fake_ainvoke(state, config):
        captured["state"] = state
        return {"draft_output": "draft", "plain_english_summary": "s", "error": None}

    graph.ainvoke = fake_ainvoke

    with (
        patch("themis.gateway.control_plane.get_graph", return_value=graph),
        patch("themis.gateway.control_plane.LexConfig") as cfg_cls,
    ):
        cfg = MagicMock()
        cfg.api_secret_key = None
        cfg.default_firm_id = "firm1"
        cfg_cls.return_value = cfg

        client.post("/api/v1/matters/M-new/message", json={"text": "brief"})

    assert captured["state"]["intake_complete"] is False


def test_send_message_resumed_matter_preserves_intake(client):
    """Resumed matter (checkpoint exists): intake_complete is NOT passed to the graph."""
    graph = _make_graph_mock()
    # aget_state returns a snapshot with values → resumed matter
    snapshot = MagicMock()
    snapshot.values = {"intake_complete": True, "draft_output": None}
    graph.aget_state = AsyncMock(return_value=snapshot)

    captured = {}

    async def fake_ainvoke(state, config):
        captured["state"] = state
        return {"draft_output": "draft", "plain_english_summary": "s", "error": None}

    graph.ainvoke = fake_ainvoke

    with (
        patch("themis.gateway.control_plane.get_graph", return_value=graph),
        patch("themis.gateway.control_plane.LexConfig") as cfg_cls,
    ):
        cfg = MagicMock()
        cfg.api_secret_key = None
        cfg.default_firm_id = "firm1"
        cfg_cls.return_value = cfg

        client.post("/api/v1/matters/M-resumed/message", json={"text": "next turn"})

    assert "intake_complete" not in captured["state"]


def test_send_message_returns_draft_on_success(client):
    """Successful graph run → status=draft_ready with draft_output."""
    graph = _make_graph_mock(draft="Full injunction draft.")
    graph.aget_state = AsyncMock(return_value=None)

    with (
        patch("themis.gateway.control_plane.get_graph", return_value=graph),
        patch("themis.gateway.control_plane.LexConfig") as cfg_cls,
    ):
        cfg = MagicMock()
        cfg.api_secret_key = None
        cfg.default_firm_id = "firm1"
        cfg_cls.return_value = cfg

        resp = client.post("/api/v1/matters/M-abc/message", json={"text": "brief"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "draft_ready"
    assert data["draft_output"] == "Full injunction draft."


def test_send_message_returns_in_progress_when_no_draft(client):
    """Graph completes but no draft_output → status=in_progress (still in intake)."""
    graph = _make_graph_mock(draft=None)
    graph.aget_state = AsyncMock(return_value=None)

    async def fake_ainvoke(state, config):
        return {"draft_output": None, "plain_english_summary": None, "error": None}

    graph.ainvoke = fake_ainvoke

    with (
        patch("themis.gateway.control_plane.get_graph", return_value=graph),
        patch("themis.gateway.control_plane.LexConfig") as cfg_cls,
    ):
        cfg = MagicMock()
        cfg.api_secret_key = None
        cfg.default_firm_id = "firm1"
        cfg_cls.return_value = cfg

        resp = client.post("/api/v1/matters/M-abc/message", json={"text": "brief"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


# ─── WebSocket auth ───────────────────────────────────────────────────────────

def test_ws_closes_4403_on_wrong_token(client):
    """ws_endpoint closes with 4403 when api_secret_key is set and token is wrong."""
    from starlette.websockets import WebSocketDisconnect

    with patch("themis.gateway.control_plane.LexConfig") as cfg_cls:
        cfg = MagicMock()
        cfg.api_secret_key = "secret"
        cfg.default_firm_id = "firm1"
        cfg_cls.return_value = cfg

        # The server rejects before accept() — TestClient raises WebSocketDisconnect
        # at context entry with code 4403.
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/user1/M-test?token=wrong"):
                pass
        assert exc_info.value.code == 4403


def test_ws_accepts_correct_token(client):
    """ws_endpoint accepts connection when a valid JWT is provided."""
    graph = _make_graph_mock()
    snapshot = MagicMock()
    snapshot.values = {}
    final_snap = MagicMock()
    final_snap.values = {"draft_output": None, "plain_english_summary": None,
                         "intake_complete": False, "error": None}
    graph.aget_state = AsyncMock(side_effect=[snapshot, final_snap])

    async def fake_stream(state, config, version):
        return
        yield  # make it an async generator

    graph.astream_events = fake_stream

    # Patch decode_access_token so the test stays offline (no python-jose needed).
    fake_claims = {"firm_id": "firm1", "sub": "user1", "role": "admin"}

    with (
        patch("themis.gateway.control_plane.get_graph", return_value=graph),
        patch("themis.gateway.control_plane.LexConfig") as cfg_cls,
        patch("themis.security.tokens.decode_access_token", return_value=fake_claims),
    ):
        cfg = MagicMock()
        cfg.api_secret_key = "secret"
        cfg.default_firm_id = "firm1"
        cfg_cls.return_value = cfg

        with client.websocket_connect("/ws/user1/M-test?token=any.valid.jwt") as ws:
            ws.send_text(json.dumps({"text": "I need to draft an injunction."}))
            done = ws.receive_json()
            assert done["type"] == "done"
