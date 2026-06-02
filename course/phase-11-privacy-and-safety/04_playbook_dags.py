"""
Phase 11, Lesson 4 — Declarative Contract Review with Playbook DAGs

Run this file: python course/phase-11-privacy-and-safety/04_playbook_dags.py
"""

# ============================================================
# THE PROBLEM
# ============================================================
#
# Every law firm has standard positions on key contract clauses.
# For NDAs: "We never accept less than 3 years confidentiality."
# For SLAs: "Liability cap must be 2x the contract value."
#
# Without a playbook, the LLM reviews the contract generically
# and may miss that a clause deviates from the firm's position.
#
# With a playbook, the review is:
#   for each position in firm_playbook:
#       detect → is this clause present?
#       grade  → does it meet our standard?
#       flag   → if not, severity + recommended redline


# ============================================================
# THE PLAYBOOK YAML FORMAT
# ============================================================
#
# lexagent/contract/defaults/nda.yaml:
#
#   id: nda
#   name: NDA — Standard Positions
#   contract_type: nda
#   positions:
#     - clause: Confidentiality period
#       our_position: 3 years from disclosure date (not execution date)
#       rationale: Execution date can precede actual disclosure by months
#     - clause: Governing law
#       our_position: Indian law, Delhi courts
#       rationale: Delhi courts have fastest injunction turnaround
#   notes: "Default to one-way NDA."

from lexagent.contract.playbook import load_playbook, load_playbook_spec, playbook_to_prompt
from lexagent.contract.models import PlaybookSpec, PlaybookPosition


# ============================================================
# LOADING PLAYBOOKS
# ============================================================

print("=== Loading the bundled NDA playbook ===\n")

# Old way (still works — returns dict)
pb_dict = load_playbook("nda")
if pb_dict:
    print(f"  load_playbook() → dict with {len(pb_dict.get('positions', []))} positions")
    print(f"  First clause: {pb_dict['positions'][0]['clause']}")

# New way (returns typed PlaybookSpec)
pb_spec = load_playbook_spec("nda")
if pb_spec:
    print(f"\n  load_playbook_spec() → PlaybookSpec with {len(pb_spec.positions)} positions")
    print(f"  First clause: {pb_spec.positions[0].clause}")
    print(f"  Our position: {pb_spec.positions[0].our_position}")
    print(f"  Rationale   : {pb_spec.positions[0].rationale}")

# Both work with playbook_to_prompt()
if pb_dict:
    prompt_from_dict = playbook_to_prompt(pb_dict)
    print(f"\n  playbook_to_prompt(dict) → {len(prompt_from_dict)} chars")

if pb_spec:
    prompt_from_spec = playbook_to_prompt(pb_spec)
    print(f"  playbook_to_prompt(spec) → {len(prompt_from_spec)} chars")
    print("\n  Prompt preview:")
    for line in prompt_from_spec.split("\n")[:6]:
        print(f"    {line}")


# ============================================================
# BUILDING A PLAYBOOK FROM SCRATCH
# ============================================================

print("\n=== Building a custom SLA playbook ===\n")

from lexagent.contract.models import PlaybookSpec, PlaybookPosition

sla_spec = PlaybookSpec(
    id="sla_v1",
    name="SLA — Standard Positions",
    contract_type="sla",
    positions=[
        PlaybookPosition(
            clause="Liability cap",
            our_position="2x the annual contract value",
            rationale="Covers implementation costs plus one year of operations",
        ),
        PlaybookPosition(
            clause="Uptime SLA",
            our_position="99.9% monthly uptime",
            rationale="Below 99.9% creates business risk",
        ),
        PlaybookPosition(
            clause="Notice period for termination",
            our_position="90 days written notice",
            rationale="Allows time to migrate to alternative vendor",
        ),
    ],
    notes="Never accept unlimited liability on our side.",
)

print(f"  Spec: {sla_spec.name}")
print(f"  Positions: {len(sla_spec.positions)}")
for p in sla_spec.positions:
    print(f"    • {p.clause}: {p.our_position}")


# ============================================================
# THE EXECUTOR (mock — no real PDF needed)
# ============================================================

print("\n=== PlaybookExecutor — what it does ===\n")

print("  For each position in the playbook, the executor sends:")
print()
print('  System: "You are a contract review assistant. Analyse the contract')
print('           for the specified clause. Return JSON with:")
print('           detected: bool, excerpt: str, deviation: str, severity: ok|minor|major|critical"')
print()
print("  User: [clause + our_position + contract text]")
print()
print("  LLM returns JSON → PositionResult stored in PlaybookExecution")
print()

from lexagent.contract.models import PlaybookExecution, PositionResult

# Simulate what a completed execution looks like
execution = PlaybookExecution(
    playbook_id="nda",
    document_path="/uploads/client_nda.pdf",
    matter_id="matter_001",
    status="completed",
    overall_risk="HIGH",
    results=[
        PositionResult(
            clause="Confidentiality period",
            our_position="3 years from disclosure date",
            detected=True,
            excerpt="confidentiality shall be maintained for 1 year from the date of agreement",
            deviation="Contract says 1 year, we require 3 years",
            severity="major",
        ),
        PositionResult(
            clause="Governing law",
            our_position="Indian law, Delhi courts",
            detected=True,
            excerpt="This agreement shall be governed by Indian law, Delhi courts",
            deviation=None,
            severity="ok",
        ),
    ],
)

print(f"  Execution result: {execution.overall_risk} risk")
summary = execution.summary()
print(f"  Positions checked: {summary['positions_checked']}")
print(f"  Deviations found:  {summary['deviations']}")
print(f"  Critical:          {summary['critical']}")
print(f"  Major:             {summary['major']}")

print()
print("  To export as xlsx (for client delivery):")
print("  executor.export_xlsx(execution, 'review_output.xlsx')")


# ============================================================
# HOW IT WIRES INTO THE AGENT
# ============================================================

print()
print("=== Integration with contract_review node ===")
print()
print("  When LEX_PLAYBOOK_EXECUTION=true:")
print("    1. contract_review node runs the inline risk report (unchanged)")
print("    2. It enqueues an AgentJob(type='playbook_review') in Postgres")
print("    3. RuntimeWorker picks it up asynchronously")
print("    4. PlaybookExecutor.run() loops through all positions")
print("    5. Results saved to playbook_executions table")
print()
print("  The main review response is NOT delayed.")
print("  The playbook run happens in the background.")
print()
print("  State field to set: state['active_playbook_id'] = 'nda'")
print("  The node reads this field to know which playbook to use.")
