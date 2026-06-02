# LANGGRAPH: Node contract — every node is an async function that:
#   1. Receives the full LexState as its only argument
#   2. Returns a dict containing ONLY the keys it changed
#   3. Never returns the full state — LangGraph merges the partial dict automatically
#   4. Never raises exceptions — catch everything and set state["error"]

import json
import re
from pathlib import Path
from typing import Optional

import yaml
from lexagent.config import LexConfig
from lexagent.memory.soul import load_soul
from lexagent.skills.loader import load_skill
from lexagent.state import LexState

# Core fields always required regardless of matter type.
_CORE_FIELDS = ["matter_type", "parties", "jurisdiction", "purpose"]

# State fields that are directly settable by question bank answers.
# Maps question field → state key (same name for most, explicit for any divergence).
_FIELD_TO_STATE: dict[str, str] = {
    "parties": "parties",
    "jurisdiction": "jurisdiction",
    "purpose": "purpose",
    "matter_type": "matter_type",
    "fundamental_right": "fundamental_right",
    "article_invoked": "article_invoked",
    "cause_of_action_date": "cause_of_action_date",
    "relief_sought": "relief_sought",
    "alternative_remedy": "alternative_remedy",
    "urgency": "urgency",
    "previous_orders": "previous_orders",
    "plaint_valuation": "plaint_valuation",
    "limitation_applicable": "limitation_applicable",
    "notice_period": "notice_period",
    "bail_type": "bail_type",
    "offence_section": "offence_section",
    "custody_duration": "custody_duration",
    "citations_required": "citations_required",
    "key_clauses": "key_clauses",
    "tone_preference": "tone_preference",
}

# Skill names for display (matter_type keyword → human label)
_SKILL_DISPLAY_NAMES: dict[str, str] = {
    "writ": "Constitutional / Writ Petition",
    "plaint": "Civil Litigation",
    "injunction": "Injunction Application",
    "legal notice": "Legal Notice",
    "bail": "Criminal Bail Application",
    "written statement": "Written Statement",
    "contract": "Contract Review",
    "affidavit": "Affidavit Drafting",
}


def _load_question_bank() -> dict:
    """Load intake_questions.yaml from the data directory."""
    data_dir = Path(__file__).parent.parent / "data"
    path = data_dir / "intake_questions.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _resolve_matter_key(matter_type: str) -> Optional[str]:
    """Map a detected matter_type string to a question bank key."""
    if not matter_type:
        return None
    mt = matter_type.lower()
    # Ordered by specificity — check more specific strings first
    if "writ" in mt or "article 226" in mt or "article 32" in mt:
        return "writ_petition"
    if "bail" in mt or "section 437" in mt or "section 438" in mt or "section 167" in mt:
        return "bail_application"
    if "injunction" in mt or "order xxxix" in mt or "interim relief" in mt:
        return "injunction"
    if "legal notice" in mt or "notice" in mt:
        return "legal_notice"
    if "written statement" in mt:
        return "written_statement"
    if "contract" in mt or "nda" in mt or "agreement" in mt or "review" in mt:
        return "contract_review"
    if "affidavit" in mt:
        return "affidavit"
    if "plaint" in mt or "civil suit" in mt or "recovery" in mt or "specific performance" in mt:
        return "plaint"
    return None


def _skill_display_name(matter_type: str) -> str:
    """Return a human-readable skill name for the matter type."""
    mt = matter_type.lower()
    for keyword, name in _SKILL_DISPLAY_NAMES.items():
        if keyword in mt:
            return name
    return matter_type.title()


def _get_unanswered_questions(
    questions: list[dict],
    state: LexState,
) -> list[dict]:
    """Return questions whose field has not yet been answered in state."""
    unanswered = []
    for q in questions:
        field = q["field"]
        state_key = _FIELD_TO_STATE.get(field, field)
        val = state.get(state_key)  # type: ignore[call-overload]
        if not val:
            unanswered.append(q)
    return unanswered


def _build_question_bank_prompt(
    matter_type: Optional[str],
    bank: dict,
    state: LexState,
    soul: Optional[dict],
) -> str:
    """
    Build the question-bank section of the system prompt.
    Includes: bank definition for the detected matter type, already-answered fields,
    and SOUL.md defaults so the LLM can pre-fill jurisdiction etc.
    """
    soul_defaults = ""
    if soul:
        preferred_court = soul.get("preferred_court") or soul.get("court", "")
        if preferred_court:
            soul_defaults = f"\nLawyer's default court from profile: {preferred_court}. Pre-fill jurisdiction if not specified."

    if not matter_type or not bank:
        return (
            "No matter type detected yet. Ask the lawyer what kind of document they need "
            "(e.g., writ petition, plaint, legal notice, bail application, injunction, contract review)."
            + soul_defaults
        )

    bank_key = _resolve_matter_key(matter_type)
    if not bank_key or bank_key not in bank:
        return (
            f"Matter type '{matter_type}' detected but no specific question bank found. "
            f"Use your knowledge of Indian litigation to ask the most relevant 4-5 questions for this matter type."
            + soul_defaults
        )

    matter_bank = bank[bank_key]
    required_qs = matter_bank.get("required", [])
    optional_qs = matter_bank.get("optional", [])

    # Build answered/unanswered summary
    all_qs = required_qs + optional_qs
    answered = []
    unanswered_required = []
    unanswered_optional = []

    for q in required_qs:
        field = q["field"]
        state_key = _FIELD_TO_STATE.get(field, field)
        val = state.get(state_key)  # type: ignore[call-overload]
        if val:
            answered.append(f"  - {field}: ANSWERED ({str(val)[:60]})")
        else:
            unanswered_required.append(q)

    for q in optional_qs:
        field = q["field"]
        state_key = _FIELD_TO_STATE.get(field, field)
        val = state.get(state_key)  # type: ignore[call-overload]
        if val:
            answered.append(f"  - {field}: ANSWERED")
        else:
            unanswered_optional.append(q)

    lines = [f"Matter type: {matter_type} (bank: {bank_key})"]
    if answered:
        lines.append("Already answered:\n" + "\n".join(answered))

    if unanswered_required:
        lines.append("REQUIRED fields still needed (ask these first):")
        for q in unanswered_required:
            opts = f" Options: {q.get('options')}" if q.get("options") else ""
            lines.append(f"  - field={q['field']} type={q['type']}{opts}\n    Question: \"{q['label']}\"")

    if not unanswered_required and unanswered_optional:
        lines.append("All required fields answered. You may ask optional fields if they add value:")
        for q in unanswered_optional[:3]:
            opts = f" Options: {q.get('options')}" if q.get("options") else ""
            lines.append(f"  - field={q['field']} type={q['type']}{opts}\n    Question: \"{q['label']}\"")

    lines.append(soul_defaults)
    return "\n".join(lines)


def _build_system_prompt(matter_type: Optional[str], bank_section: str) -> str:
    return f"""You are LexAgent's intake specialist for Indian lawyers.

Your job: collect enough information to draft a court-ready legal document.

Rules:
- Never ask for information already provided in the conversation.
- Ask a maximum of 5 questions per turn — fewer if possible.
- Ask REQUIRED questions first, then optional ones.
- Use the exact question text from the bank where provided.
- SOUL.md defaults (e.g. preferred court) can pre-fill fields without asking.

--- QUESTION BANK ---
{bank_section}
--- END BANK ---

Respond ONLY with a JSON object in this exact format:
{{
  "matter_type": "<extracted or null>",
  "parties": {{"description": "<extracted or null>"}},
  "jurisdiction": "<extracted or null>",
  "purpose": "<extracted or null>",
  "extracted_fields": {{
    "<field_name>": "<value extracted from conversation>"
  }},
  "clarifying_questions": [
    {{
      "field": "<field name>",
      "question": "<question text>",
      "type": "open|binary|mcq",
      "options": ["option1", "option2"]
    }}
  ]
}}

Rules for clarifying_questions:
- Include "options" only for type=mcq questions; omit for open and binary.
- For type=binary, options are always ["Yes", "No"] — do not include them in JSON.
- If all required fields are present, set clarifying_questions to [].
- Do not invent fields outside the bank — use the exact field names from the bank.
"""


async def run(state: LexState) -> dict:
    """
    Intake node: collects required matter information from the lawyer.

    Phase 8 changes:
    - Loads per-matter-type question bank from intake_questions.yaml
    - LLM receives the bank and selects unanswered questions adaptively
    - Returns structured clarifying_questions objects (with type/options for Telegram buttons)
    - Emits active_skill_name for visible skill loading in Telegram
    """
    try:
        if _all_core_fields_present(state) and _matter_type_complete(state):
            # Fast-exit: all fields already present. Still load the skill so the
            # draft node gets it — skipping this was why skills never applied to
            # well-specified briefs.
            updates: dict = {"intake_complete": True}
            if not state.get("active_skill"):
                config = LexConfig()
                bundled_skills = Path(__file__).parent.parent / "skills"
                skill_content = load_skill(
                    state.get("matter_type") or "",
                    bundled_skills_dir=bundled_skills,
                    user_skills_dir=config.skills_dir,
                )
                if skill_content:
                    updates["active_skill"] = skill_content
                    updates["active_skill_name"] = _skill_display_name(state.get("matter_type") or "")
            return updates

        config = LexConfig()

        lawyer_soul = state.get("lawyer_soul")
        if not lawyer_soul:
            lawyer_soul = load_soul(config.home_dir)

        # Load question bank
        question_bank = _load_question_bank()
        matter_type = state.get("matter_type")

        bank_section = _build_question_bank_prompt(matter_type, question_bank, state, lawyer_soul)
        system_prompt = _build_system_prompt(matter_type, bank_section)

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": state["user_input"]})
        for msg in state.get("messages", []):
            messages.append(msg)

        from lexagent.nodes._llm import call_llm
        result = await call_llm(
            messages,
            config,
            model_override=config.chat_model,
            matter_id=state.get("matter_id"),
        )
        response_text = result["content"]
        extracted = _parse_extraction(response_text)

        updates: dict = {
            "messages": list(state.get("messages", [])) + [{"role": "assistant", "content": response_text}],
            "intake_complete": False,
            "lawyer_soul": lawyer_soul,
        }

        # Apply extracted core fields
        if extracted.get("matter_type"):
            updates["matter_type"] = extracted["matter_type"]

            # Load matching skill
            bundled_skills = Path(__file__).parent.parent / "skills"
            skill_content = load_skill(
                extracted["matter_type"],
                bundled_skills_dir=bundled_skills,
                user_skills_dir=config.skills_dir,
            )
            if skill_content:
                updates["active_skill"] = skill_content
                updates["active_skill_name"] = _skill_display_name(extracted["matter_type"])

        if extracted.get("parties"):
            updates["parties"] = extracted["parties"]
        if extracted.get("jurisdiction"):
            updates["jurisdiction"] = extracted["jurisdiction"]
        if extracted.get("purpose"):
            updates["purpose"] = extracted["purpose"]

        # Apply any additional extracted fields (from deep question bank answers)
        for field, value in (extracted.get("extracted_fields") or {}).items():
            state_key = _FIELD_TO_STATE.get(field, field)
            if state_key and value:
                updates[state_key] = value  # type: ignore[literal-required]

        # Structured questions for Telegram inline keyboard rendering
        raw_questions = extracted.get("clarifying_questions", [])
        if raw_questions:
            updates["pending_questions"] = raw_questions
            # Also populate legacy plain-text list for non-Telegram consumers
            updates["clarifying_questions"] = [q["question"] if isinstance(q, dict) else q for q in raw_questions]

        # T1-D: one-shot fast-path — complete immediately when all core fields are
        # present AND the LLM itself decided no questions are needed.
        # WHY: _matter_type_complete() requires every question bank field (e.g.
        # fundamental_right, bail_type) which a concise brief won't include.
        # Trusting the LLM's own empty-question judgement avoids unnecessary friction
        # while still respecting question bank requirements when fields are genuinely absent.
        merged = {**state, **updates}
        if _all_core_fields_present(merged):
            if not raw_questions:
                # LLM sees enough — proceed without any questions
                updates["intake_complete"] = True
                updates["pending_questions"] = []
                updates["clarifying_questions"] = []
            elif _matter_type_complete(merged):
                # Full question bank satisfied
                updates["intake_complete"] = True
                updates["pending_questions"] = []
                updates["clarifying_questions"] = []

        return updates

    except Exception as e:
        return {"error": f"Intake node failed: {e}", "intake_complete": False}


def _all_core_fields_present(state: LexState) -> bool:
    return all(bool(state.get(f)) for f in _CORE_FIELDS)


def _matter_type_complete(state: LexState) -> bool:
    """
    Check if all required fields for the detected matter type are present.
    Falls back to core-fields-only check if no question bank matches.
    """
    matter_type = state.get("matter_type")
    if not matter_type:
        return False

    bank_key = _resolve_matter_key(matter_type)
    if not bank_key:
        return True  # no bank → core fields are enough

    bank = _load_question_bank()
    if bank_key not in bank:
        return True

    required_qs = bank[bank_key].get("required", [])
    for q in required_qs:
        field = q["field"]
        state_key = _FIELD_TO_STATE.get(field, field)
        if not state.get(state_key):  # type: ignore[call-overload]
            return False
    return True


def _parse_extraction(content: str) -> dict:
    """
    Parse the LLM's JSON response. Strips markdown fences, handles malformed JSON.
    """
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "clarifying_questions": [
                {
                    "field": "purpose",
                    "question": "Could you describe the matter you need help with?",
                    "type": "open",
                }
            ]
        }
