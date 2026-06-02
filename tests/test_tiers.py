"""Tests for lexagent/security/tiers.py and lexagent/gateway/tier_middleware.py."""
from __future__ import annotations

import pytest

from lexagent.security.tiers import (
    InferenceTier,
    TierFloorConfig,
    TierViolation,
    check_tier,
    tier_for_provider,
)


# ---------------------------------------------------------------------------
# TierFloorConfig.effective_floor()
# ---------------------------------------------------------------------------

def test_effective_floor_firm_only():
    cfg = TierFloorConfig(firm_floor=4)
    assert cfg.effective_floor() == 4


def test_effective_floor_matter_stricter():
    cfg = TierFloorConfig(firm_floor=4, matter_floor=2)
    assert cfg.effective_floor() == 2


def test_effective_floor_skill_stricter():
    cfg = TierFloorConfig(firm_floor=4, skill_floor=3)
    assert cfg.effective_floor() == 3


def test_effective_floor_all_three_takes_min():
    cfg = TierFloorConfig(firm_floor=4, matter_floor=2, skill_floor=3)
    assert cfg.effective_floor() == 2


def test_effective_floor_none_values_ignored():
    cfg = TierFloorConfig(firm_floor=3, matter_floor=None, skill_floor=None)
    assert cfg.effective_floor() == 3


# ---------------------------------------------------------------------------
# check_tier()
# ---------------------------------------------------------------------------

def test_check_tier_passes_when_equal():
    cfg = TierFloorConfig(firm_floor=4)
    check_tier(4, cfg)  # should not raise


def test_check_tier_passes_when_stricter():
    cfg = TierFloorConfig(firm_floor=4)
    check_tier(1, cfg)  # Tier 1 is stricter than floor 4


def test_check_tier_raises_when_weaker():
    cfg = TierFloorConfig(firm_floor=3)
    with pytest.raises(TierViolation) as exc_info:
        check_tier(4, cfg)
    assert exc_info.value.requested == 4
    assert exc_info.value.floor == 3


def test_check_tier_raises_consumer_on_standard_floor():
    cfg = TierFloorConfig(firm_floor=4)
    with pytest.raises(TierViolation):
        check_tier(5, cfg)


def test_check_tier_consumer_allowed_when_floor_is_5():
    cfg = TierFloorConfig(firm_floor=5)
    check_tier(5, cfg)  # should not raise


# ---------------------------------------------------------------------------
# TierViolation exception attributes
# ---------------------------------------------------------------------------

def test_tier_violation_attributes():
    exc = TierViolation(requested=4, floor=3)
    assert exc.requested == 4
    assert exc.floor == 3
    assert "4" in str(exc)
    assert "3" in str(exc)


def test_tier_violation_message_contains_labels():
    exc = TierViolation(requested=5, floor=1)
    msg = str(exc)
    assert "consumer" in msg.lower() or "5" in msg
    assert "local" in msg.lower() or "1" in msg


# ---------------------------------------------------------------------------
# tier_for_provider()
# ---------------------------------------------------------------------------

def test_tier_for_known_providers():
    assert tier_for_provider("ollama") == 1
    assert tier_for_provider("lmstudio") == 1
    assert tier_for_provider("custom") == 2
    assert tier_for_provider("azure") == 3
    assert tier_for_provider("bedrock") == 3
    assert tier_for_provider("nvidia") == 3
    assert tier_for_provider("anthropic") == 4
    assert tier_for_provider("openai") == 4
    assert tier_for_provider("gemini") == 4
    assert tier_for_provider("groq") == 5


def test_tier_for_unknown_provider_defaults_to_4():
    assert tier_for_provider("some_unknown_provider") == 4


# ---------------------------------------------------------------------------
# TierFloorMiddleware (unit test without running FastAPI)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tier_middleware_passes_compliant_tier(monkeypatch):
    """Middleware allows request when tier meets the firm floor."""
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("LEX_INFERENCE_TIER_FLOOR", "4")

    from lexagent.gateway.tier_middleware import TierFloorMiddleware

    app = MagicMock()
    middleware = TierFloorMiddleware(app)

    request = MagicMock()
    request.headers = {"X-Inference-Tier": "3"}  # Tier 3 meets floor 4 (stricter)
    request.state = MagicMock()

    call_next = AsyncMock(return_value=MagicMock())
    await middleware.dispatch(request, call_next)
    call_next.assert_awaited_once()
    assert request.state.inference_tier == 3


@pytest.mark.asyncio
async def test_tier_middleware_blocks_weaker_tier(monkeypatch):
    """Middleware returns 403 when tier is weaker than floor."""
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("LEX_INFERENCE_TIER_FLOOR", "3")

    from lexagent.gateway.tier_middleware import TierFloorMiddleware
    from fastapi.responses import JSONResponse

    app = MagicMock()
    middleware = TierFloorMiddleware(app)

    request = MagicMock()
    request.headers = {"X-Inference-Tier": "5"}  # Tier 5 < floor 3
    request.state = MagicMock()

    call_next = AsyncMock()
    response = await middleware.dispatch(request, call_next)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_tier_middleware_no_header_sets_default(monkeypatch):
    """No X-Inference-Tier header → sets state to firm floor."""
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("LEX_INFERENCE_TIER_FLOOR", "2")

    from lexagent.gateway.tier_middleware import TierFloorMiddleware

    app = MagicMock()
    middleware = TierFloorMiddleware(app)

    request = MagicMock()
    request.headers = {}
    request.state = MagicMock()

    call_next = AsyncMock(return_value=MagicMock())
    await middleware.dispatch(request, call_next)
    assert request.state.inference_tier == 2


@pytest.mark.asyncio
async def test_tier_middleware_invalid_header_returns_400(monkeypatch):
    """Non-integer X-Inference-Tier returns 400."""
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("LEX_INFERENCE_TIER_FLOOR", "4")

    from lexagent.gateway.tier_middleware import TierFloorMiddleware
    from fastapi.responses import JSONResponse

    app = MagicMock()
    middleware = TierFloorMiddleware(app)

    request = MagicMock()
    request.headers = {"X-Inference-Tier": "not_a_number"}
    request.state = MagicMock()

    call_next = AsyncMock()
    response = await middleware.dispatch(request, call_next)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
