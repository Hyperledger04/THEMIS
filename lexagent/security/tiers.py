"""
Privacy tier floor enforcement.

Inspired by LQ.AI's five-tier inference classification system. Tiers are
integers so Python's built-in < and >= work for comparisons: lower integer
= stricter privacy (Tier 1 is most private; Tier 5 is least private).

Usage:
    config = TierFloorConfig(firm_floor=3)
    check_tier(4, config)  # raises TierViolation — Tier 4 is weaker than floor 3
    check_tier(2, config)  # passes — Tier 2 is stricter than floor 3
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class InferenceTier(IntEnum):
    LOCAL_ONLY = 1          # Ollama / air-gapped — data never leaves the machine
    SELF_HOSTED = 2         # Cloud keys encrypted in gateway; compute stays on-prem
    ENTERPRISE_MANAGED = 3  # Azure / Bedrock / Vertex with zero-data-retention BAA
    STANDARD_CLOUD = 4      # Anthropic / OpenAI standard commercial terms
    CONSUMER = 5            # Free / consumer endpoints — disabled by default


# Human-readable labels for logs and error messages
TIER_LABELS: dict[int, str] = {
    1: "local-only (Ollama / air-gapped)",
    2: "self-hosted (on-prem keys)",
    3: "enterprise-managed (zero-data-retention BAA)",
    4: "standard cloud (commercial terms)",
    5: "consumer / free (globally restricted)",
}

# Default tier assigned to each provider name.
# Keyed by the provider name in profiles.py.
PROVIDER_TIERS: dict[str, int] = {
    "ollama":    1,
    "lmstudio":  1,
    "custom":    2,   # self-hosted OpenAI-compat endpoint
    "azure":     3,
    "bedrock":   3,
    "nvidia":    3,   # NIM enterprise contracts typically include zero-retention
    "anthropic": 4,
    "openai":    4,
    "gemini":    4,
    "mistral":   4,
    "xai":       4,
    "openrouter":4,
    "together":  4,
    "deepseek":  4,
    "groq":      5,   # has a free tier; treat as Tier 5 until firm upgrades plan
}


class TierViolation(Exception):
    """Raised when a requested inference tier is weaker than the effective floor."""

    def __init__(self, requested: int, floor: int) -> None:
        self.requested = requested
        self.floor = floor
        req_label = TIER_LABELS.get(requested, str(requested))
        floor_label = TIER_LABELS.get(floor, str(floor))
        super().__init__(
            f"Inference tier {requested} ({req_label}) is weaker than "
            f"the minimum floor {floor} ({floor_label}). "
            "Upgrade the provider or lower the tier floor."
        )


@dataclass(frozen=True)
class TierFloorConfig:
    """
    Composable tier floor from three sources.

    effective_floor() returns the strictest (lowest integer) of:
      firm_floor   — set in LexConfig (applies to the whole deployment)
      matter_floor — set per-matter in the workspace model (privileged matters)
      skill_floor  — declared in skill YAML frontmatter as min_inference_tier
    """
    firm_floor: int = 4
    matter_floor: Optional[int] = None
    skill_floor: Optional[int] = None

    def effective_floor(self) -> int:
        """Return the strictest (lowest integer) floor from all sources."""
        candidates = [self.firm_floor]
        if self.matter_floor is not None:
            candidates.append(self.matter_floor)
        if self.skill_floor is not None:
            candidates.append(self.skill_floor)
        return min(candidates)


def check_tier(requested: int, floor_config: TierFloorConfig) -> None:
    """
    Raise TierViolation if requested tier is weaker than the effective floor.

    Lower integer = stricter privacy. A request for Tier 4 (standard cloud)
    when the floor is Tier 3 (enterprise-managed) is a violation because
    4 > 3 — the cloud provider does not meet the minimum privacy requirement.
    """
    floor = floor_config.effective_floor()
    if requested > floor:
        raise TierViolation(requested, floor)


def tier_for_provider(provider_name: str) -> int:
    """
    Return the default inference tier for a named provider.

    Unknown providers default to Tier 4 (standard cloud).
    """
    return PROVIDER_TIERS.get(provider_name, 4)
