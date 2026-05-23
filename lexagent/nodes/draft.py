# Draft node: generates the full legal document from intake data.
# Phase 1 produces a clean draft without research (no real citations yet).
# Phase 3 adds: skill injection, matter memory in user turn, LiteLLM caching.
# Phase 4 will enrich with verified case law from research_findings.

import importlib.resources
from pathlib import Path
from typing import Optional

import litellm
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from lexagent.config import LexConfig
from lexagent.nodes._llm import get_llm
from lexagent.state import LexState


# ---------------------------------------------------------------------------
# Phase 3: Caching helpers
# ---------------------------------------------------------------------------


def inject_memory_into_user_turn(user_input: str, matter_memory: Optional[str]) -> str:
    """
    Prepend matter memory to the user's request — for ALL providers.

    WHY user turn and not system prompt:
    The system prompt (SOUL.md + skill) must stay identical across all turns
    so the cache hit rate stays high. Matter memory changes per session, so
    if it were in the system prompt the cache would miss on every turn.

    The <memory-context> XML tag tells the model this is background context,
    not a new instruction — LLMs respond well to this framing convention.
    """
    if not matter_memory:
        return user_input
    return f"<memory-context>\n{matter_memory}\n</memory-context>\n\n{user_input}"


def build_system_prompt_blocks(
    soul: Optional[dict],
    skill_content: Optional[str],
    use_cache_control: bool,
) -> "list | str":
    """
    Build the system prompt in the format needed for the chosen caching path.

    use_cache_control=True  → returns a list of content blocks with cache_control.
                              Used with litellm.acompletion() when provider=anthropic.
                              Anthropic's servers cache this block → ~10% cost on cache hits.

    use_cache_control=False → returns a plain string.
                              Used with ChatLiteLLM for all other providers.
                              LiteLLM's disk cache (Layer 1) still applies.
    """
    # Build the combined content: SOUL.md first, then skill
    parts = []
    if soul and soul.get("raw"):
        parts.append(f"## Your Lawyer Profile\n{soul['raw']}")
    elif soul and isinstance(soul, str):
        parts.append(f"## Your Lawyer Profile\n{soul}")

    if skill_content:
        parts.append(f"## Active Skill\n{skill_content}")

    combined = "\n\n---\n\n".join(parts) if parts else ""

    if use_cache_control:
        # ANTHROPIC / LITELLM: cache_control marks this block for server-side caching.
        # Anthropic caches up to 4 breakpoints per request. TTL is 5 minutes.
        # A cache HIT on the system prompt costs ~10% of normal input token price.
        return [
            {
                "type": "text",
                "text": combined,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    return combined


# ---------------------------------------------------------------------------
# Internal helpers (unchanged from Phase 2)
# ---------------------------------------------------------------------------


def _load_prompt(filename: str) -> str:
    """
    Load a prompt template from the prompts/ directory.

    WHY: Prompts live in .md files, not inline strings. This means:
    - Non-engineers can edit prompts without touching Python code
    - Prompts can be version-controlled and reviewed independently
    - Future UI can expose prompt editing to lawyers directly
    """
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_path = prompts_dir / filename
    return prompt_path.read_text(encoding="utf-8")


def _build_string_system_prompt(state: LexState, base_prompt: str) -> str:
    """
    Build the string-form system prompt for non-Anthropic providers.
    Injects SOUL.md and active skill into the base template placeholders.
    """
    matter_type = state.get("matter_type") or "Not specified"
    parties = state.get("parties") or {}
    jurisdiction = state.get("jurisdiction") or "Not specified"
    purpose = state.get("purpose") or "Not specified"

    if isinstance(parties, dict):
        parties_str = "; ".join(f"{k}: {v}" for k, v in parties.items() if v)
    else:
        parties_str = str(parties)

    soul_section = build_system_prompt_blocks(
        soul=state.get("lawyer_soul"),
        skill_content=state.get("active_skill"),
        use_cache_control=False,
    )

    return (
        base_prompt
        .replace("{matter_type}", matter_type)
        .replace("{parties}", parties_str)
        .replace("{jurisdiction}", jurisdiction)
        .replace("{purpose}", purpose)
        .replace("{lawyer_soul_section}", soul_section or "## Your Lawyer Profile\nNo profile loaded. Run `lex setup`.")
        .replace("{active_skill_section}", "")  # already embedded in soul_section combined output
    )


def _build_draft_instruction(state: LexState) -> str:
    """Build the user-turn drafting instruction, personalised with lawyer name."""
    lawyer_soul = state.get("lawyer_soul")
    lawyer_name = ""
    if isinstance(lawyer_soul, dict):
        lawyer_name = lawyer_soul.get("name", "")

    instruction = (
        f"Please draft the legal document for the following matter"
        f"{f' for {lawyer_name}' if lawyer_name else ''}:\n\n"
        f"Matter type: {state.get('matter_type')}\n"
        f"Parties: {state.get('parties')}\n"
        f"Jurisdiction: {state.get('jurisdiction')}\n"
        f"Purpose: {state.get('purpose')}\n"
    )

    if state.get("key_clauses"):
        instruction += f"Key clauses/reliefs required: {', '.join(state['key_clauses'])}\n"

    if state.get("tone_preference"):
        instruction += f"Tone: {state['tone_preference']}\n"

    research = state.get("research_findings")
    if research:
        # WHY: RAPTOR summary entries are structural summaries injected into
        # research_findings; they have no citation and use 'snippet' not 'relevance'.
        # Including them in the instruction would cause KeyError and pollute citation
        # extraction with None values. Filter them out — they inform chunking, not drafting.
        citable = [r for r in research if r.get("citation")]
        instruction += "\n\nVerified case law to use:\n" + "\n".join(
            f"- {r['case_name']} ({r['citation']}): {r.get('relevance', r.get('snippet', ''))}"
            for r in citable
        )
    else:
        instruction += (
            "\n\nIMPORTANT: No pre-verified research is available for this draft. "
            "Only cite cases you are highly confident exist. "
            "Flag any citation you include as [UNVERIFIED — human review required] "
            "since the citation verification node has not run."
        )

    instruction += "\n\nAfter the document, provide a Plain English Summary (2-3 sentences for the client)."
    return instruction


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------


async def run(state: LexState) -> dict:
    """
    Draft node: produces a full legal document from the intake fields.

    Phase 3 additions:
    - Active skill content injected into system prompt
    - Matter memory injected into user turn (keeps system prompt cache-stable)
    - Anthropic: uses litellm.acompletion() with cache_control for Layer 2 caching
    - All providers: LiteLLM disk cache (Layer 1) from setup_litellm_cache()

    Input state must have: matter_type, parties, jurisdiction, purpose, intake_complete=True
    Output: draft_output, plain_english_summary
    """
    try:
        config = LexConfig()
        draft_instruction = _build_draft_instruction(state)

        # Always inject matter memory into the user turn — for ALL providers.
        # WHY user turn: see inject_memory_into_user_turn() docstring.
        from lexagent.memory.matter_memory import load_matter_memory
        matter_id = state.get("matter_id")
        matter_mem = load_matter_memory(matter_id, config.matters_dir) if matter_id else None
        draft_instruction = inject_memory_into_user_turn(draft_instruction, matter_mem)

        use_anthropic_caching = (
            config.model_provider == "anthropic"
            and config.enable_prompt_caching
        )

        if use_anthropic_caching:
            # Layer 2: Anthropic server-side prompt caching via litellm.acompletion()
            # WHY direct litellm call: ChatLiteLLM passes system as a string.
            # litellm.acompletion() accepts native Anthropic content block format,
            # including cache_control — this is the only way to get Layer 2 via LiteLLM.
            system_blocks = build_system_prompt_blocks(
                soul=state.get("lawyer_soul"),
                skill_content=state.get("active_skill"),
                use_cache_control=True,
            )
            messages = [
                {"role": "system", "content": system_blocks},
                {"role": "user", "content": draft_instruction},
            ]
            response = await litellm.acompletion(
                model=f"{config.model_provider}/{config.default_model}",
                messages=messages,
                caching=config.enable_prompt_caching,
            )
            full_output = response.choices[0].message.content
        else:
            # Layer 1 only: ChatLiteLLM (any provider) + LiteLLM disk cache
            base_prompt = _load_prompt("base_system.md")
            system_prompt_str = _build_string_system_prompt(state, base_prompt)

            messages = [
                SystemMessage(content=system_prompt_str),
                HumanMessage(content=draft_instruction),
            ]
            llm = get_llm(config)
            response = await llm.ainvoke(messages)
            full_output = response.content

        summary = _extract_summary(full_output)

        return {
            "draft_output": full_output,
            "plain_english_summary": summary,
            "messages": [AIMessage(content=full_output)],
        }

    except Exception as e:
        return {"error": f"Draft node failed: {e}"}


def _extract_summary(draft_text: str) -> str:
    """
    Pull the plain English summary out of the draft if the LLM included one.
    Returns the full text if no clear summary section is found.
    """
    import re

    match = re.search(
        r"(?:Plain English Summary|CLIENT SUMMARY|Summary for client)[:\s]*\n+(.*?)(?:\n\n|$)",
        draft_text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return ""
