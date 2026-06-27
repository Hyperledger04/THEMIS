# Draft node: generates the full legal document from intake data.
# Phase 1 produces a clean draft without research (no real citations yet).
# Phase 3 adds: skill injection, matter memory in user turn, LiteLLM caching.
# Phase 4 will enrich with verified case law from research_findings.
# T1-A: live token streaming via asyncio.Queue side-channel.

import asyncio
import importlib.resources
from pathlib import Path
from typing import Optional

import litellm

from themis.config import LexConfig
from themis.state import SeniorCounselState


# ---------------------------------------------------------------------------
# Live streaming registry
# WHY: asyncio.Queue can't live in TypedDict (not JSON-serializable).
# The chat/CLI layer pre-registers a queue keyed by matter_id before
# graph.astream(). draft.run() looks up the queue and writes tokens to it.
# Sentinel None signals stream end.
# ---------------------------------------------------------------------------

_DRAFT_STREAMS: dict[str, asyncio.Queue] = {}


def register_draft_stream(matter_id: str) -> asyncio.Queue:
    """Pre-register a token queue before graph.astream(). Returns the queue."""
    q: asyncio.Queue = asyncio.Queue()
    _DRAFT_STREAMS[matter_id] = q
    return q


def get_draft_stream(matter_id: str) -> Optional[asyncio.Queue]:
    return _DRAFT_STREAMS.get(matter_id)


def unregister_draft_stream(matter_id: str) -> None:
    _DRAFT_STREAMS.pop(matter_id, None)


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
    agent: Optional[dict] = None,
    wisdom_text: Optional[str] = None,
) -> "list | str":
    """
    Build the system prompt in the format needed for the chosen caching path.

    use_cache_control=True  → returns a list of content blocks with cache_control.
                              Used with litellm.acompletion() when provider=anthropic.
                              Anthropic's servers cache this block → ~10% cost on cache hits.

    use_cache_control=False → returns a plain string.
                              Used with litellm.acompletion() for all other providers.
                              LiteLLM's disk cache (Layer 1) still applies.

    agent → if an active_agent persona is set, its persona description is injected
            between SOUL.md and the skill so the model embodies the agent's character.
    """
    # Build the combined content: SOUL.md → agent persona → skill
    parts = []
    if soul and soul.get("raw"):
        parts.append(
            f"## Your Lawyer Profile\n{soul['raw']}\n\n"
            "**IMPORTANT:** This profile describes YOU — the lawyer using Themis. "
            "It is NOT necessarily the signing advocate for this document. "
            "If the matter brief or parties specify a different advocate (e.g. 'through Adv. Neha Arora'), "
            "use that advocate's name and details in the signature block, not your profile name."
        )
    elif soul and isinstance(soul, str):
        parts.append(
            f"## Your Lawyer Profile\n{soul}\n\n"
            "**IMPORTANT:** This profile describes YOU — the lawyer using Themis. "
            "If the matter brief specifies a different signing advocate, use their details in the document."
        )

    # WHY: Agent persona comes after SOUL (which grounds identity) but before skill
    # (which governs structure) so the model knows WHO it is before HOW to draft.
    if agent and agent.get("persona"):
        agent_name = agent.get("full_name") or agent.get("name") or agent["id"]
        tone_line = f"\n**Tone:** {agent['tone']}" if agent.get("tone") else ""
        parts.append(
            f"## Active Advocate Persona — @{agent['id']}\n"
            f"You are embodying the persona of **{agent_name}**."
            f"{tone_line}\n\n"
            f"{agent['persona']}"
        )

    if skill_content:
        parts.append(f"## Active Skill\n{skill_content}")

    if wisdom_text and wisdom_text.strip():
        parts.append(f"## Learned from Past Similar Matters\n{wisdom_text}")

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


def _build_string_system_prompt(state: SeniorCounselState, base_prompt: str, wisdom_text: Optional[str] = None) -> str:
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
        agent=state.get("active_agent"),
        wisdom_text=wisdom_text,
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


def _build_draft_instruction(state: SeniorCounselState) -> str:
    """Build the user-turn drafting instruction, personalised with lawyer name and agent."""
    lawyer_soul = state.get("lawyer_soul")
    lawyer_name = ""
    if isinstance(lawyer_soul, dict):
        lawyer_name = lawyer_soul.get("name", "")

    active_agent = state.get("active_agent")
    agent_note = ""
    if active_agent:
        agent_name = active_agent.get("full_name") or active_agent.get("name") or active_agent["id"]
        agent_note = f" You are drafting as {agent_name} — embody this persona fully."

    instruction = (
        f"Please draft the legal document for the following matter"
        f"{f' for {lawyer_name}' if lawyer_name else ''}.{agent_note}\n\n"
        f"Matter type: {state.get('matter_type')}\n"
        f"Parties: {state.get('parties')}\n"
        f"Jurisdiction: {state.get('jurisdiction')}\n"
        f"Purpose: {state.get('purpose')}\n"
    )

    if state.get("key_clauses"):
        instruction += f"Key clauses/reliefs required: {', '.join(state['key_clauses'])}\n"

    if state.get("tone_preference"):
        instruction += f"Tone: {state['tone_preference']}\n"

    # Include the full matter brief so specific details (cheque numbers, bank accounts,
    # advocate names, addresses, dates, etc.) are all available to the model.
    # This is the source of truth — always prefer details from here over generic placeholders.
    user_input = state.get("user_input", "")
    if user_input:
        instruction += (
            f"\n\n--- FULL MATTER BRIEF (use ALL specific details from this) ---\n"
            f"{user_input}\n"
            f"--- END BRIEF ---\n"
            "\nNever leave placeholders like [INSERT ...] if the detail is present above. "
            "Fill every field you have data for. Only use a placeholder when the detail is genuinely absent."
        )

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
            "Do NOT place [UNVERIFIED] tags inside the document body — that is unprofessional. "
            "Instead, list any citations you are uncertain about in a separate section after "
            "the Plain English Summary, headed **Citations Requiring Verification**. "
            "The document body must read as a clean, professional legal document."
        )

    # ── RAG: inject retrieved template and past-draft examples ───────────────
    # WHY: template_chunks ground the document structure in a gold-standard format,
    # eliminating the numbered-header and formatting issues from generic prompts.
    # past_draft_chunks provide stylistic continuity across similar matters.
    retrieval_chunks = state.get("retrieval_chunks") or []
    template_chunks = [c for c in retrieval_chunks if c.get("type") == "template"]
    past_draft_chunks = [c for c in retrieval_chunks if c.get("type") == "past_draft"]

    if template_chunks:
        instruction = (
            "\n\n--- REFERENCE TEMPLATE (follow this structure and format exactly) ---\n"
            + template_chunks[0]["content"]
            + "\n--- END TEMPLATE ---\n\n"
            "Draft the document following the above template's structure, formatting, and tone. "
            "Adapt it to the specific facts of this matter — fill in every placeholder with "
            "real details from the matter brief. Never leave placeholder text like '[___]' "
            "if the information is available above.\n\n"
            + instruction
        )

    if past_draft_chunks:
        instruction += "\n\n--- EXAMPLES FROM PAST SIMILAR MATTERS (style reference only) ---\n"
        for chunk in past_draft_chunks[:2]:
            instruction += f"\n[From matter {chunk['source']}]:\n{chunk['content'][:800]}\n"
        instruction += "--- END EXAMPLES ---\n"

    # ── Exhibit registry injection ────────────────────────────────────────
    # WHY: If an exhibit registry was built during intake, the LLM must use
    # these labels verbatim throughout the document. Without this instruction
    # the LLM invents its own labels (e.g. "Annexure A") which will conflict
    # with the separately-generated affidavit and list of documents.
    exhibit_registry = state.get("exhibit_registry") or {}
    if exhibit_registry:
        exhibit_lines = "\n".join(
            f"  {key.replace('_', ' ').title()}: {label}"
            for key, label in exhibit_registry.items()
        )
        instruction += (
            f"\n\nEXHIBIT LABELS (use these exactly — do not invent alternatives):\n"
            f"{exhibit_lines}\n"
            f"Every reference to a document in the filing body must use the label above. "
            f"Never use 'Annexure A' or any other format."
        )

    # ── S.141 NI Act: conditional block for firm/company accused ──────────
    # WHY: S.141 extends criminal liability to proprietors, partners, and
    # directors. Without this explicit instruction, the LLM does not fire the
    # S.141 paragraph because it doesn't know the accused entity type.
    # This must be injected here — not left to general prompt guidance —
    # because the accused_entity_type field is intake-derived, not LLM-inferred.
    accused_entity_type = state.get("accused_entity_type") or ""
    if accused_entity_type.lower() in ("proprietorship", "partnership", "company"):
        instruction += (
            f"\n\nIMPORTANT — SECTION 141 NI ACT (MANDATORY):\n"
            f"The accused is a {accused_entity_type}. You MUST include a dedicated paragraph "
            f"invoking Section 141 of the Negotiable Instruments Act, 1881 AFTER the accused "
            f"identity paragraph and BEFORE the cause-of-action paragraph.\n"
            f"This paragraph must:\n"
            f"  1. State that the named individual(s) were personally responsible for and in "
            f"     charge of the day-to-day conduct of the business of the {accused_entity_type}.\n"
            f"  2. Invoke joint and several liability under S.138 read with S.141 NI Act.\n"
            f"Do NOT skip this paragraph — its absence is a ground for acquittal of the "
            f"proprietor/partner/director."
        )

    instruction += "\n\nAfter the document, provide a Plain English Summary (2-3 sentences for the client)."
    return instruction


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------


async def run(state: SeniorCounselState) -> dict:
    """
    Draft node: produces a full legal document from the intake fields.

    Phase 3 additions:
    - Active skill content injected into system prompt
    - Matter memory injected into user turn (keeps system prompt cache-stable)
    - Anthropic: uses litellm.acompletion() with cache_control for Layer 2 caching
    - All providers: LiteLLM disk cache (Layer 1) from setup_litellm_cache()

    T1-A: tokens are pushed live to _DRAFT_STREAMS[matter_id] so the chat/CLI
    layer can print them character-by-character while the graph runs.

    Input state must have: matter_type, parties, jurisdiction, purpose, intake_complete=True
    Output: draft_output, plain_english_summary
    """
    matter_id = state.get("matter_id", "")
    stream_q = get_draft_stream(matter_id)
    try:
        config = LexConfig()
        draft_instruction = _build_draft_instruction(state)

        # Always inject matter memory into the user turn — for ALL providers.
        # WHY user turn: see inject_memory_into_user_turn() docstring.
        from themis.memory.matter_memory import load_matter_memory
        firm_id = state.get("firm_id") or config.default_firm_id
        matter_mem = load_matter_memory(matter_id, config.matters_dir, firm_id=firm_id) if matter_id else None
        draft_instruction = inject_memory_into_user_turn(draft_instruction, matter_mem)

        use_anthropic_caching = (
            config.model_provider == "anthropic"
            and config.enable_prompt_caching
        )

        wisdom_text = ""
        try:
            from themis.memory.wisdom import get_relevant_wisdom
            wisdom_text = get_relevant_wisdom(
                matter_type=state.get("matter_type"),
                jurisdiction=state.get("jurisdiction"),
                home_dir=config.home_dir,
                max_entries=6,
            )
        except Exception:
            pass

        full_output = ""

        if use_anthropic_caching:
            # Layer 2: Anthropic server-side prompt caching via litellm.acompletion()
            # WHY content blocks: litellm.acompletion() accepts native Anthropic content block
            # format including cache_control — this is the only way to get Layer 2 caching.
            system_blocks = build_system_prompt_blocks(
                soul=state.get("lawyer_soul"),
                skill_content=state.get("active_skill"),
                use_cache_control=True,
                agent=state.get("active_agent"),
                wisdom_text=wisdom_text,
            )
            messages = [
                {"role": "system", "content": system_blocks},
                {"role": "user", "content": draft_instruction},
            ]
            response = await litellm.acompletion(
                model=f"{config.model_provider}/{config.default_model}",
                messages=messages,
                caching=config.enable_prompt_caching,
                stream=True,
            )
            async for chunk in response:
                token = (chunk.choices[0].delta.content) or ""
                if token:
                    full_output += token
                    if stream_q is not None:
                        await stream_q.put(token)
        else:
            # Layer 1 only: direct litellm streaming (any provider) + LiteLLM disk cache
            base_prompt = _load_prompt("base_system.md")
            system_prompt_str = _build_string_system_prompt(state, base_prompt, wisdom_text=wisdom_text)

            messages = [
                {"role": "system", "content": system_prompt_str},
                {"role": "user", "content": draft_instruction},
            ]
            model_str = f"{config.model_provider}/{config.default_model}"
            stream_kwargs: dict = {"model": model_str, "messages": messages, "stream": True}
            if config.model_base_url:
                stream_kwargs["api_base"] = config.model_base_url
            response = await litellm.acompletion(**stream_kwargs)
            async for chunk in response:
                token = (chunk.choices[0].delta.content) or ""
                if token:
                    full_output += token
                    if stream_q is not None:
                        await stream_q.put(token)

        summary = _extract_summary(full_output)

        result: dict = {
            "draft_output": full_output,
            "plain_english_summary": summary,
            "messages": list(state.get("messages", [])) + [{"role": "assistant", "content": full_output}],
        }

        # ── Affidavit sub-document for S.138 complaints ───────────────────
        # WHY: S.138 summary trials under S.143 NI Act take evidence by affidavit.
        # The affidavit IS the examination-in-chief — without it the complainant
        # has a pleading but no evidence document. It must be a separate document,
        # not a verification clause embedded in the complaint body.
        # Only generated for S.138 — other matter types use inline verification.
        matter_type = state.get("matter_type") or ""
        if _is_s138_matter(matter_type):
            affidavit_text = await _generate_affidavit(state, config, full_output)
            if affidavit_text:
                result["affidavit_output"] = affidavit_text

        return result

    except Exception as e:
        return {"error": f"Draft node failed: {e}"}
    finally:
        # Always send sentinel so the consumer never hangs waiting for more tokens.
        if stream_q is not None:
            await stream_q.put(None)


def _is_s138_matter(matter_type: str) -> bool:
    mt = matter_type.lower()
    return "138" in mt or "s138" in mt or "cheque" in mt or "ni act" in mt or "dishonour" in mt


async def _generate_affidavit(state: SeniorCounselState, config: "LexConfig", complaint_draft: str) -> str:
    """
    Generate an Evidence by Affidavit for S.138 NI Act complaints.

    This is a second LLM call, separate from the main draft call.
    The affidavit is the complainant's sworn examination-in-chief in a summary
    trial under S.143 NI Act. It must:
      - Be in first person (the complainant speaks)
      - Have 12-14 numbered paragraphs restating the complaint facts
      - Reference each exhibit by its canonical label from the exhibit registry
      - End with a verification block for the oath commissioner

    WHY second call (not part of the main draft call):
    Combining them would require the LLM to switch voice mid-document (third person
    for the complaint, first person for the affidavit), which degrades quality.
    Separate calls with targeted instructions produce better-structured output.
    """
    parties = state.get("parties") or {}
    complainant_name = (
        parties.get("complainant")
        or parties.get("plaintiff")
        or parties.get("petitioner")
        or "the Complainant"
    )

    exhibit_registry = state.get("exhibit_registry") or {}
    exhibit_lines = "\n".join(
        f"  {key.replace('_', ' ').title()}: {label}"
        for key, label in exhibit_registry.items()
    ) if exhibit_registry else "  Use EX-CW1/A, EX-CW1/B, etc. for exhibits"

    affidavit_instruction = (
        f"You are drafting an EVIDENCE BY AFFIDAVIT for {complainant_name} (CW-1) "
        f"to be filed in an S.138 NI Act complaint.\n\n"
        f"This is NOT the complaint — it is the complainant's sworn testimony, "
        f"written in first person. It is the examination-in-chief in the summary trial.\n\n"
        f"Rules:\n"
        f"1. Write 12-14 numbered paragraphs in FIRST PERSON (I, me, my).\n"
        f"2. Restate all facts from the complaint in first-person sworn form.\n"
        f"3. Refer to each document by its exhibit label from this registry:\n"
        f"{exhibit_lines}\n"
        f"4. State that all exhibited documents are true copies of the originals.\n"
        f"5. End with a VERIFICATION block:\n"
        f"   'I, {complainant_name}, do hereby solemnly affirm that the contents "
        f"of this affidavit are true and correct to the best of my knowledge and belief.'\n"
        f"6. Add a signature block for the Deponent and a blank for the Oath Commissioner.\n\n"
        f"The complaint text to base this affidavit on:\n\n{complaint_draft[:4000]}\n\n"
        f"Draft the Evidence by Affidavit now. Write only the affidavit — no preamble."
    )

    try:
        response = await litellm.acompletion(
            model=f"{config.model_provider}/{config.default_model}",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior Indian litigation advocate. "
                        "Draft court documents precisely and concisely."
                    ),
                },
                {"role": "user", "content": affidavit_instruction},
            ],
            stream=False,
        )
        return response.choices[0].message.content or ""
    except Exception:
        return ""


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
