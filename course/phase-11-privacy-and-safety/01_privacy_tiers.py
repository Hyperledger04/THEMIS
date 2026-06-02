"""
Phase 11, Lesson 1 — The Five-Tier Inference Model

Run this file: python course/phase-11-privacy-and-safety/01_privacy_tiers.py
"""

# ============================================================
# WHY TIERS?
# ============================================================
#
# Not all LLM providers handle your data the same way.
# When you send a client's case facts to an API, the question
# "where does this data go?" has very different answers:
#
#   Ollama (local)   → data never leaves your laptop
#   Azure OpenAI     → Microsoft enterprise contract, zero-retention BAA
#   Anthropic API    → standard commercial terms, may use for training
#   Groq (free tier) → consumer endpoint, minimal data commitments
#
# LexAgent models this as a 5-tier integer scale.
# Lower = stricter. Higher = weaker privacy.

from lexagent.security.tiers import (
    InferenceTier,
    TierFloorConfig,
    TierViolation,
    check_tier,
    tier_for_provider,
)


# ============================================================
# THE FIVE TIERS
# ============================================================

print("=== The Five Tiers ===")
for tier in InferenceTier:
    print(f"  Tier {tier.value}: {tier.name}")

# Output:
#   Tier 1: LOCAL_ONLY
#   Tier 2: SELF_HOSTED
#   Tier 3: ENTERPRISE_MANAGED
#   Tier 4: STANDARD_CLOUD
#   Tier 5: CONSUMER


# ============================================================
# PROVIDER TIERS
# ============================================================

print("\n=== Provider Tiers ===")
providers = ["ollama", "lmstudio", "custom", "azure", "bedrock",
             "anthropic", "openai", "gemini", "mistral", "groq"]
for p in providers:
    print(f"  {p:15} → Tier {tier_for_provider(p)}")


# ============================================================
# TIER FLOOR CHECK
# ============================================================
#
# TierFloorConfig composes three independent floors.
# effective_floor() returns the STRICTEST (lowest integer).
#
#   firm_floor   → set in LexConfig for the whole deployment
#   matter_floor → per-matter override (privileged client)
#   skill_floor  → declared in skill YAML frontmatter

print("\n=== TierFloorConfig ===")

# Firm allows standard cloud (Tier 4), matter requires enterprise (Tier 3)
cfg = TierFloorConfig(firm_floor=4, matter_floor=3)
print(f"  firm=4, matter=3 → effective floor = {cfg.effective_floor()}")  # 3

# Skill declares min_inference_tier: 1 (local only)
cfg2 = TierFloorConfig(firm_floor=4, skill_floor=1)
print(f"  firm=4, skill=1  → effective floor = {cfg2.effective_floor()}")  # 1


# ============================================================
# WHAT HAPPENS WHEN A TIER VIOLATION FIRES
# ============================================================

print("\n=== Tier Violation ===")

cfg = TierFloorConfig(firm_floor=3)  # enterprise minimum

# Groq is Tier 5 — below the floor
try:
    check_tier(tier_for_provider("groq"), cfg)
except TierViolation as e:
    print(f"  BLOCKED: {e}")

# Azure is Tier 3 — exactly at the floor → allowed
try:
    check_tier(tier_for_provider("azure"), cfg)
    print("  ALLOWED: azure (Tier 3 meets floor 3)")
except TierViolation:
    print("  This should not happen")

# Ollama is Tier 1 — stricter than floor → allowed
try:
    check_tier(tier_for_provider("ollama"), cfg)
    print("  ALLOWED: ollama (Tier 1 is stricter than floor 3)")
except TierViolation:
    print("  This should not happen")


# ============================================================
# HOW THE MIDDLEWARE USES THIS
# ============================================================
#
# Every request to the FastAPI control plane passes through
# TierFloorMiddleware (lexagent/gateway/tier_middleware.py).
#
# 1. Read X-Inference-Tier header (optional int)
# 2. Load TierFloorConfig(firm_floor=cfg.inference_tier_floor)
# 3. check_tier(header_tier, floor_config)
# 4. TierViolation → 403 JSON response
# 5. Pass → set request.state.inference_tier and continue
#
# The CLI (lex draft) bypasses the middleware entirely —
# it calls call_llm() directly. Tiers only gate the HTTP API.

print("\n=== Summary ===")
print("  Lower tier integer = stricter privacy")
print("  check_tier(requested, floor) raises TierViolation when requested > floor")
print("  TierFloorMiddleware enforces this on every FastAPI request")
print("  Set LEX_INFERENCE_TIER_FLOOR=3 to require enterprise providers")
