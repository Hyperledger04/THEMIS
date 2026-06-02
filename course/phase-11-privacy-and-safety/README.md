# Phase 11 — Privacy, Safety, and Production Hardening

> **What this phase is about:** LexAgent can now draft, research, and review contracts. But running it for a real law firm — with real client data — requires three things that most tutorial projects skip entirely: privacy controls, cost safety, and structured contract review pipelines.
>
> This phase adds all three, inspired by the open-source [LQ.AI](https://github.com/LegalQuants/lq-ai) federated inference architecture.

---

## The Problem

You have a working legal AI. A lawyer runs `lex draft "NI Act cheque bounce matter"` and gets a court-ready document. Now ask yourself:

- **Where did the client's name go?** It went to Anthropic's servers in the US. Is that okay for a privileged legal matter?
- **What if the agent runs for 3 hours?** Overnight research loops can cost $50+. Who stops it?
- **The firm has a standard NDA position.** How does the AI know not to accept anything less than 3 years confidentiality?

These are not edge cases. They are the reasons law firms don't deploy legal AI in production.

---

## What You Will Learn

### `01_privacy_tiers.py` — The Five-Tier Inference Model
- Why not all LLM providers are equal from a privacy standpoint
- The 5-tier classification (local → enterprise-managed → consumer)
- How `TierFloorConfig` composes firm-wide, matter-level, and skill-level floors
- Reading real code: `lexagent/security/tiers.py`

### `02_anonymization_gateway.py` — PII Anonymization Before Cloud Calls
- Why you cannot just "trust" the LLM provider's data policy
- How pseudonymization works: `PERSON_0`, `ORG_0`, case numbers → restore on response
- The `InferenceGateway` as a single choke-point between nodes and the LLM
- Reading real code: `lexagent/gateway/anonymizer.py`, `lexagent/gateway/inference.py`

### `03_runtime_brakes.py` — Cost Caps, Halt Flags, Phase Gates
- The three runtime brakes and when each fires
- `CostLedger`: per-model token accounting, session vs. job caps
- `HaltFlag`: external cancellation + idle watchdog
- `PhaseGate`: restricts which tools are callable in each workflow phase
- Reading real code: `lexagent/runtime/brakes.py`

### `04_playbook_dags.py` — Declarative Contract Review
- Why hardcoded review logic does not scale across matter types
- Playbook YAML format: clause → our position → rationale
- The detect→grade loop: `PlaybookExecutor.run()`
- Exporting results as xlsx for client delivery
- Reading real code: `lexagent/contract/executor.py`, `lexagent/contract/models.py`

---

## The Architecture in One Diagram

```
Lawyer request
      │
      ▼
FastAPI Control Plane
      │
      ├─ TierFloorMiddleware ──────── 403 if provider tier < firm floor
      │
      ▼
call_llm()  [lexagent/nodes/_llm.py]
      │
      ├─ anonymization_enabled? ─── Yes → InferenceGateway.call()
      │                                        │
      │                           anonymize → LLM → restore → log
      │
      ▼
RuntimeWorker  [lexagent/runtime/worker.py]
      │
      ├─ CostLedger.record() ──────── raises CostCapReached if over budget
      ├─ HaltFlag.should_halt() ───── returns "external_halt" | "idle_timeout"
      └─ PhaseGate.check() ────────── raises PhaseViolation if wrong phase

contract_review node
      │
      └─ playbook_execution_enabled? → enqueue AgentJob("playbook_review")
                                              │
                                              ▼
                                       PlaybookExecutor.run()
                                       detect → grade → export xlsx
```

---

## Key Design Decisions (and Why)

**Why integers for tiers, not strings?**
Python's `<` and `>=` work on integers. `tier_4 > tier_3` is immediately readable. String comparisons like `"enterprise" > "standard"` require a lookup table.

**Why middleware instead of per-endpoint decorators?**
A missed decorator is a silent bypass. Middleware is unconditional — every request goes through it, even ones you forgot to protect.

**Why `load_skill_with_tier()` alongside `load_skill()` instead of changing the original?**
11 tests depend on `load_skill()` returning `Optional[str]`. Changing the return type would break them all. A parallel function with a new name costs one extra function definition and breaks nothing.

**Why `inspect.signature()` in the worker?**
Existing handlers take `(job, repo)`. New handlers can opt in to `ledger` and `halt_flag` by declaring them. The worker detects this at call time — no registry, no decorator, no migration of existing handlers.

**Why `playbook_to_prompt()` accepts both dict and PlaybookSpec?**
Three CLI callers pass dicts. The new executor passes a typed model. An `isinstance` branch in one function serves both — no caller migration needed.

---

## How to Explore the Code

```bash
# Run the new tests
pytest tests/test_tiers.py tests/test_brakes.py -v

# Try the tier check directly
python -c "
from lexagent.security.tiers import TierFloorConfig, check_tier, TierViolation
cfg = TierFloorConfig(firm_floor=3)
try:
    check_tier(5, cfg)  # Groq — consumer tier
except TierViolation as e:
    print(e)
"

# See what tier each provider is
python -c "
from lexagent.providers.profiles import list_profiles
for p in list_profiles():
    print(f'{p.name:15} tier={p.inference_tier}')
"

# Build and run a playbook review (needs a PDF)
python -c "
import asyncio
from lexagent.contract.playbook import load_playbook_spec
from lexagent.contract.executor import PlaybookExecutor

spec = load_playbook_spec('nda')
print(spec)
"
```

---

## Files Added in This Phase

| File | What it does |
|---|---|
| `lexagent/security/tiers.py` | 5-tier classification, `TierFloorConfig`, `check_tier`, `TierViolation` |
| `lexagent/gateway/tier_middleware.py` | FastAPI middleware enforcing the firm floor |
| `lexagent/gateway/anonymizer.py` | Presidio-based PII pseudonymization + restore |
| `lexagent/gateway/inference.py` | Single choke-point between nodes and LLM |
| `lexagent/gateway/recognizers.py` | Indian legal PII recognizers (case numbers, matter IDs) |
| `lexagent/runtime/brakes.py` | `CostLedger`, `HaltFlag`, `PhaseGate` |
| `lexagent/runtime/migrations/003_brakes.sql` | ALTER TABLE for cost/halt columns |
| `lexagent/runtime/migrations/004_playbooks.sql` | `playbook_executions` table |
| `lexagent/contract/models.py` | `PlaybookSpec`, `PlaybookExecution`, `PositionResult` |
| `lexagent/contract/repository.py` | Postgres persistence for playbook runs |
| `lexagent/contract/executor.py` | Detect→grade loop, xlsx export |
| `tests/test_tiers.py` | 18 tests for tier enforcement |
| `tests/test_brakes.py` | 19 tests for runtime brakes |
| `tests/test_playbook_models.py` | 11 tests for playbook models |
| `tests/test_executor.py` | 9 tests for the executor |
| `tests/test_anonymizer.py` | 16 tests for PII anonymization |
