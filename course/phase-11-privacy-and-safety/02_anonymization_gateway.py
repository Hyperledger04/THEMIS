"""
Phase 11, Lesson 2 — PII Anonymization Before Cloud LLM Calls

Run this file: python course/phase-11-privacy-and-safety/02_anonymization_gateway.py

NOTE: Full anonymization requires presidio-analyzer and spacy.
      Run: pip install presidio-analyzer presidio-anonymizer spacy
           python -m spacy download en_core_web_lg
      This lesson shows the architecture even if those deps are missing.
"""

# ============================================================
# THE PROBLEM
# ============================================================
#
# When a lawyer runs:
#   lex draft "Advise Ramesh Gupta (M/s Gupta Exports) on cheque bounce"
#
# The client's name and company go directly to the LLM API.
# Standard commercial terms (Anthropic, OpenAI) allow data to be
# used for model improvement unless you have an enterprise BAA.
#
# For a law firm, sending client names and matter facts to a
# third-party server is a potential privilege breach.
#
# Solution: pseudonymize BEFORE the API call, restore AFTER.

# ============================================================
# THE ANONYMIZATION FLOW
# ============================================================
#
# Messages in:
#   [{"role": "user", "content": "Advise Ramesh Gupta (M/s Gupta Exports)..."}]
#
# After anonymize():
#   [{"role": "user", "content": "Advise PERSON_0 (ORG_0)..."}]
#   pseudonym_map = {"PERSON_0": "Ramesh Gupta", "ORG_0": "M/s Gupta Exports"}
#
# LLM sees: "Advise PERSON_0 (ORG_0)..."
# LLM responds: "PERSON_0's position under Section 138 NI Act..."
#
# After restore():
#   "Ramesh Gupta's position under Section 138 NI Act..."

print("=== Anonymization Architecture ===")
print()
print("  messages → LegalAnonymizer.anonymize() → [anon_messages, pmap]")
print("  anon_messages → LLM API (no real names)")
print("  LLM response → LegalAnonymizer.restore(response, pmap)")
print("  restored response → lawyer")
print()


# ============================================================
# TRY THE ANONYMIZER (if presidio is installed)
# ============================================================

try:
    from lexagent.gateway.anonymizer import LegalAnonymizer

    anon = LegalAnonymizer()
    messages = [
        {
            "role": "user",
            "content": (
                "Advise Ramesh Gupta of M/s Gupta Exports Pvt Ltd on a "
                "cheque bounce matter. The cheque was drawn on HDFC Bank "
                "account ending 4821."
            ),
        }
    ]

    anon_messages, pmap = anon.anonymize(messages)
    print("=== Anonymized messages ===")
    print(f"  Original : {messages[0]['content'][:80]}...")
    print(f"  Anonymized: {anon_messages[0]['content'][:80]}...")
    print(f"  Pseudonym map: {pmap}")

    # Simulate LLM response using pseudonyms
    fake_llm_response = (
        f"Based on the facts, {list(pmap.keys())[0] if pmap else 'PERSON_0'} "
        "has a strong case under Section 138 NI Act."
    )
    restored = anon.restore(fake_llm_response, pmap)
    print(f"\n  LLM said   : {fake_llm_response}")
    print(f"  Restored   : {restored}")

except ImportError:
    print("  (presidio not installed — showing architecture only)")
    print("  Install: pip install presidio-analyzer presidio-anonymizer spacy")
    print("           python -m spacy download en_core_web_lg")


# ============================================================
# THE INFERENCE GATEWAY
# ============================================================
#
# LegalAnonymizer handles PII. InferenceGateway wraps the whole
# LLM call: anonymize → call → restore → log.
#
# Key design rule:
#   inference.py imports ONLY from lexagent.config and lexagent.security.
#   It NEVER imports from lexagent.nodes or lexagent.graph.
#   This prevents circular imports (nodes import inference; inference ≠ nodes).

print()
print("=== InferenceGateway is OFF by default ===")
print()
print("  anonymization_enabled = False  (default)")
print("  → call_llm() skips the gateway entirely")
print("  → zero overhead, zero Presidio dependency at startup")
print()
print("  To enable: LEX_ANONYMIZATION_ENABLED=true")
print()
print("  Bypasses (even when enabled):")
print("  → is_document_context=True (contract PDFs — real names needed)")
print("  → matter_id in LEX_PRIVILEGED_MATTERS (verified citation drafts)")


# ============================================================
# INDIAN LEGAL PII: CASE NUMBERS AND MATTER IDS
# ============================================================
#
# Standard Presidio recognizes names, phones, emails.
# Indian legal work has additional PII:
#   - Case numbers: "CS(COMM) 42/2024", "WP 1234/2023 (Delhi HC)"
#   - Matter IDs: "matter_abc123"
#
# lexagent/gateway/recognizers.py adds two custom Presidio recognizers
# for these patterns so they get pseudonymized like any other PII.

print()
print("=== Indian Legal Recognizers ===")
try:
    from lexagent.gateway.recognizers import CaseNumberRecognizer, MatterIdRecognizer
    print("  CaseNumberRecognizer — matches: CS(COMM) 42/2024, WP 1234/2023")
    print("  MatterIdRecognizer   — matches: matter_abc123, matter-xyz")
    print("  Both are registered with Presidio's AnalyzerEngine automatically.")
except ImportError:
    print("  (recognizers available at lexagent/gateway/recognizers.py)")
