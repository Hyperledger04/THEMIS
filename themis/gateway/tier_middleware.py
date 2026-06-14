"""
FastAPI middleware that enforces the inference tier floor on every request.

The floor is set in LexConfig.inference_tier_floor (env: LEX_INFERENCE_TIER_FLOOR).
Callers may pass an optional X-Inference-Tier header to declare the tier of the
provider they intend to use. The middleware rejects the request if that tier is
weaker (higher integer) than the effective firm floor.

WHY middleware instead of a per-endpoint dependency:
  The tier check is a cross-cutting security control. A missed per-endpoint
  decorator is a silent bypass; middleware is unconditional.

Tier integers: 1=local-only (strictest) … 5=consumer/free (weakest).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from themis.config import LexConfig
from themis.security.tiers import TierFloorConfig, TierViolation, check_tier


class TierFloorMiddleware(BaseHTTPMiddleware):
    """
    Reads X-Inference-Tier from the request header (optional int).
    Loads the firm floor from LexConfig and calls check_tier().
    On TierViolation → 403. On pass → sets request.state.inference_tier.

    Personal mode (multi_tenant=False): firm floor still applies so solo
    lawyers cannot accidentally route to a weaker tier than they configured.
    """

    async def dispatch(self, request: Request, call_next):
        cfg = LexConfig()
        floor_config = TierFloorConfig(firm_floor=cfg.inference_tier_floor)

        # Parse optional caller-declared tier from header
        header_val: Optional[str] = request.headers.get("X-Inference-Tier")
        requested_tier: Optional[int] = None
        if header_val is not None:
            try:
                requested_tier = int(header_val)
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "invalid_tier_header", "detail": "X-Inference-Tier must be an integer 1–5"},
                    status_code=400,
                )

        if requested_tier is not None:
            try:
                check_tier(requested_tier, floor_config)
            except TierViolation as exc:
                return JSONResponse(
                    {
                        "error": "tier_below_minimum",
                        "requested": exc.requested,
                        "floor": exc.floor,
                        "detail": str(exc),
                    },
                    status_code=403,
                )
            request.state.inference_tier = requested_tier
        else:
            # No header — default to the firm floor (effective minimum)
            request.state.inference_tier = floor_config.effective_floor()

        return await call_next(request)
