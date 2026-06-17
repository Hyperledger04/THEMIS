"""
Themis natural language chat interface.
Uses LiteLLM for streaming so it works with any configured provider
(Anthropic, OpenAI, Gemini, Ollama, OpenRouter — whatever is in .env).

T1-A: Draft tokens streamed live via asyncio.Queue side-channel in draft.py.
T1-B: Chat history persisted per-day in SQLite; restored on startup.
T1-C: Recent matters injected into system prompt on startup.
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import litellm
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from themis.config import LexConfig

console = Console()

_SYSTEM_PROMPT = """You are Themis, an AI assistant built for Indian lawyers.

You help with:
- Drafting legal documents (legal notices, writ petitions, bail applications, plaints, injunctions, etc.)
- Researching Indian case law and statutes
- Managing and retrieving past matters

TOOLS:
- draft_document — call ONCE when you have: matter type, parties, jurisdiction, purpose. Pack ALL known details (advocate name, cheque numbers, dates, bank details, addresses, etc.) into the brief parameter.
- save_document — call this to write the last draft to disk. Pass the matter_id and a filename (e.g. "Notice_RajeshKumar.docx"). Call this automatically whenever the user says "download", "save", "export", or "generate PDF/file".
- research_law — research-only, no draft produced
- list_matters — list all saved matter files
- show_matter — retrieve a specific matter's memory by ID
- search_knowledge_base — full-text search across all past research

BEHAVIOUR:
- Be concise. Lawyers are time-poor.
- Reference specific Indian statutes (S.138 NI Act, CPC Order 39 Rule 1, IPC S.420, etc.)
- Use ₹ for rupees
- CRITICAL — NEVER call draft_document more than once per matter. Once a draft is produced, do NOT redraft unless the user explicitly says "redraft" or "start over". Instead, answer questions and clarifications in plain text.
- CRITICAL — When a draft is produced, immediately offer to save it: "Shall I save this to your Downloads folder? If yes, give me a filename."
- If draft_document returns NEEDS_MORE_INFO, ask those questions naturally, then call draft_document ONCE MORE with matter_id from the first call and a complete brief.
- After saving, confirm the file path.
"""

# ---------------------------------------------------------------------------
# Per-session draft cache — matter_id → draft text.
# Prevents the LLM from re-running the full graph when it calls draft_document
# a second time for the same matter (e.g. after user confirmations).
# ---------------------------------------------------------------------------
_DRAFT_CACHE: dict[str, str] = {}

# LiteLLM / OpenAI tool format (works across all providers)
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "draft_document",
            "description": (
                "Draft a court-ready legal document. Call ONCE when brief is complete.\n\n"
                "Required for ALL matters: matter_type, parties, jurisdiction, purpose.\n\n"
                "Collect these BEFORE calling based on matter type:\n"
                "  LEGAL NOTICE: demand amount, cause of action date, notice period\n"
                "  WRIT PETITION: article invoked (226/32), fundamental right violated,\n"
                "                 alternative remedy exhausted (yes/no), relief sought\n"
                "  BAIL APPLICATION: offence sections, bail type (regular/anticipatory/default), custody duration\n"
                "  PLAINT: court valuation (₹), limitation applicable (yes/no), specific reliefs\n"
                "  CONTRACT/NDA: key clauses, duration, governing law\n"
                "  INJUNCTION: urgency, irreparable harm facts\n\n"
                "Pack ALL known details into the brief — dates, amounts, names, addresses, cheque/account numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "brief": {
                        "type": "string",
                        "description": "Complete brief with matter type, parties, jurisdiction, purpose, and any other relevant details",
                    },
                    "matter_id": {
                        "type": "string",
                        "description": "Optional — continue an existing matter by its ID (M-XXXXXXXX)",
                    },
                },
                "required": ["brief"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_law",
            "description": "Research Indian case law and statutes. Returns relevant cases and citations without producing a draft.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Legal research question"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_matters",
            "description": "List all saved matters for this lawyer.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_matter",
            "description": "Show the memory and details of a specific saved matter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "matter_id": {"type": "string", "description": "Matter ID (e.g. M-ABCD1234)"},
                },
                "required": ["matter_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search past research and case law across all saved matters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_limitation",
            "description": (
                "Calculate limitation period under Limitation Act 1963. "
                "Call when lawyer asks if a matter is time-barred or mentions a cause of action date. "
                "Returns: applicable article, period, expiry date, time-barred status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "matter_type": {"type": "string"},
                    "cause_of_action_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD or natural language",
                    },
                },
                "required": ["matter_type", "cause_of_action_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_document",
            "description": (
                "Save the last produced draft to the user's Downloads folder as a .docx file. "
                "Call this when the user says 'download', 'save', 'export', 'generate PDF', or gives a filename. "
                "Returns the full file path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "matter_id": {
                        "type": "string",
                        "description": "Matter ID of the draft to save (e.g. M-45432C38)",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Output filename (e.g. S138-Notice_RajeshKumar.docx). Always use .docx extension.",
                    },
                },
                "required": ["matter_id", "filename"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# T1-C: Build a context-aware system prompt with recent matters injected.
# ---------------------------------------------------------------------------


def _build_chat_system_prompt(recent_matters: list[dict], cfg: LexConfig) -> str:
    """Inject SOUL identity and recent matter summaries into the base system prompt."""
    from themis.memory.soul import load_soul

    soul = load_soul(cfg.home_dir)
    identity_block = ""
    if soul and isinstance(soul, dict):
        identity_block = (
            "## LAWYER IDENTITY\n"
            f"Assisting: {soul.get('name', '')}, {soul.get('firm_name', '')}\n"
            f"Courts: {soul.get('primary_courts', '')}\n"
            f"Practice: {soul.get('practice_areas', '')}\n"
            f"Tone: {soul.get('tone', 'Senior formal')}\n"
            "Use this identity in all signature blocks unless the brief specifies otherwise.\n\n"
        )

    matters_block = ""
    if recent_matters:
        lines = []
        for m in recent_matters:
            try:
                days_ago = (datetime.now() - datetime.fromisoformat(m["created_at"])).days
                age = f"{days_ago}d ago" if days_ago > 0 else "today"
            except Exception:
                age = ""
            lines.append(
                f"  • {m.get('matter_id','?')}: {m.get('matter_type','?')}, "
                f"{m.get('jurisdiction','?')} [{age}]"
            )
        matters_block = "\n\nRECENT MATTERS (refer to by ID when the lawyer asks):\n" + "\n".join(lines)

    return identity_block + _SYSTEM_PROMPT + matters_block


async def run_chat(cfg: LexConfig) -> None:
    """Main entry point — starts the interactive chat loop."""
    # WHY: chat_model lets lawyers use a cheaper/faster model (e.g. Haiku, gpt-4o-mini)
    # for conversational turns while the full model is still used inside _tool_draft.
    # Falls back to the default model if chat_model is not set.
    chat_model = getattr(cfg, "chat_model", None) or f"{cfg.model_provider}/{cfg.default_model}"

    # T1-B: load persistent history — one session window per calendar day.
    from themis.memory.session_store import (
        get_today_session_id,
        init_db,
        list_sessions,
        load_chat_history,
        save_chat_message,
    )
    init_db(cfg.sessions_db)
    session_id = get_today_session_id()
    history_limit = getattr(cfg, "chat_history_limit", 20)
    messages: list[dict] = load_chat_history(session_id, history_limit, cfg.sessions_db)

    # T1-C: load recent matters for context injection.
    recent_matters = list_sessions(limit=3, sessions_db=cfg.sessions_db)
    system_prompt = _build_chat_system_prompt(recent_matters, cfg)

    # Auto-inject the most recent matter's full state so the LLM can answer
    # "load the last matter" without needing a show_matter tool call to succeed.
    if recent_matters:
        last_mid = recent_matters[0].get("matter_id")
        if last_mid:
            try:
                last_matter_text = _tool_show_matter(last_mid, cfg)
                system_prompt = system_prompt + (
                    f"\n\nMOST RECENT MATTER (auto-loaded, ID: {last_mid}):\n{last_matter_text}"
                )
            except Exception:
                pass

    # T2-D: inject practice wisdom accumulated from past drafts.
    # WHY: Wisdom is loaded once at startup — cheap read, high value for the LLM.
    try:
        from themis.memory.wisdom import get_relevant_wisdom
        wisdom_text = get_relevant_wisdom(
            matter_type=None,  # no specific matter yet at startup
            jurisdiction=None,
            home_dir=cfg.home_dir,
        )
        if wisdom_text:
            system_prompt = system_prompt + "\n\n" + wisdom_text
    except Exception:
        pass

    # WHY prompt_toolkit instead of Rich's Prompt.ask():
    # prompt_toolkit enables bracketed paste mode automatically. Pasting 100+ lines
    # arrives as one atomic event instead of character-by-character through readline,
    # which causes the apparent freeze. It also gives us async input (prompt_async)
    # so the event loop stays free while waiting for user input.
    session: PromptSession = PromptSession(
        style=Style.from_dict({"prompt": "bold ansicyan"}),
    )

    # Build startup panel — show restored history count + recent matters
    resumed = f"  [dim]({len(messages)} messages restored)[/dim]" if messages else ""
    recent_lines = ""
    if recent_matters:
        items = []
        for i, m in enumerate(recent_matters):
            try:
                days_ago = (datetime.now() - datetime.fromisoformat(m["created_at"])).days
                age = f"{days_ago}d ago" if days_ago > 0 else "today"
            except Exception:
                age = ""
            label = " [cyan](loaded)[/cyan]" if i == 0 else ""
            items.append(f"[dim]  • {m.get('matter_id','?')}: {m.get('matter_type','?')} [{age}][/dim]{label}")
        recent_lines = "\n[dim]Recent matters:[/dim]\n" + "\n".join(items)

    console.print()
    console.print(
        Panel(
            f"[bold cyan]⚖ Themis[/bold cyan]  Natural Language Mode{resumed}\n"
            "[dim]Draft documents, research case law, review contracts — just ask.\n"
            "Type [bold]exit[/bold] to quit.[/dim]"
            + recent_lines,
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()

    while True:
        try:
            user_input = await session.prompt_async(HTML("<bold><ansicyan>You</ansicyan></bold>  "))
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        stripped = user_input.strip()
        if not stripped:
            continue
        if stripped.lower() in ("exit", "quit", "bye", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        messages.append({"role": "user", "content": stripped})
        # T1-B: persist user turn immediately so it survives an unexpected exit.
        save_chat_message(session_id, "user", stripped, cfg.sessions_db)

        from themis.agent.loop import ThemisLoop
        loop = ThemisLoop(
            model=chat_model,
            tools=_TOOLS,
            execute_tool=_execute_tool,
            cfg=cfg,
            system=system_prompt,
        )
        new_messages = await loop.run(messages)
        messages.extend(new_messages)

        # T1-B: persist assistant turns (text only — skip tool internals).
        for msg in new_messages:
            if msg.get("role") == "assistant" and msg.get("content"):
                save_chat_message(session_id, "assistant", str(msg["content"]), cfg.sessions_db)

        console.print()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _execute_tool(
    name: str,
    inputs: dict,
    cfg: LexConfig,
    messages: list[dict] | None = None,
) -> str:
    if name == "draft_document":
        return await _tool_draft(inputs.get("brief", ""), inputs.get("matter_id"), cfg, messages)
    if name == "save_document":
        return await _tool_save_document(inputs.get("matter_id", ""), inputs.get("filename", ""), cfg)
    if name == "research_law":
        return await _tool_research(inputs.get("query", ""), cfg)
    if name == "list_matters":
        return _tool_list_matters(cfg)
    if name == "show_matter":
        return _tool_show_matter(inputs.get("matter_id", ""), cfg)
    if name == "search_knowledge_base":
        return _tool_search_kb(inputs.get("query", ""), cfg)
    if name == "check_limitation":
        from themis.tools.limitation import check_limitation
        result = check_limitation(
            matter_type=inputs.get("matter_type", ""),
            cause_of_action_date=inputs.get("cause_of_action_date", ""),
        )
        if isinstance(result, dict):
            return "\n".join(f"  {k}: {v}" for k, v in result.items())
        return str(result)
    return f"Unknown tool: {name}"


async def _tool_draft(
    brief: str,
    matter_id: Optional[str],
    cfg: LexConfig,
    messages: list[dict] | None = None,
) -> str:
    from themis.graph import get_graph
    from themis.nodes.draft import register_draft_stream, unregister_draft_stream

    mid = matter_id or f"M-{uuid.uuid4().hex[:8].upper()}"

    # If we already have a draft for this matter, return it immediately.
    # This prevents the LLM from re-running the full graph on user confirmations.
    if mid in _DRAFT_CACHE:
        return f"[Matter ID: {mid}] (existing draft — not re-generated)\n\n{_DRAFT_CACHE[mid]}"

    graph = get_graph(cfg)

    # Build a comprehensive brief that includes ALL conversation context so the
    # draft node sees specific details (cheque numbers, bank accounts, advocate
    # names, addresses, etc.) that might only appear in earlier messages.
    full_context = brief
    if messages:
        user_turns = [
            m["content"] for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ][-12:]  # last 12 user messages covers a full matter intake
        if user_turns:
            conversation_text = "\n\n".join(user_turns)
            full_context = (
                f"{brief}\n\n"
                f"[Conversation context — use ALL specific details from here]\n"
                f"{conversation_text}"
            )

    state: dict = {
        "user_input": full_context,
        "matter_id": mid,
        "intake_complete": False,
        "citations_verified": False,
        "research_only": False,
        "messages": [{"role": "user", "content": full_context}],
    }

    # Strategy announcement — one cheap LLM call before the pipeline starts.
    # WHY: The lawyer sees the agent's legal strategy immediately instead of
    # staring at a silent spinner for 90 seconds (Hermes "think out loud" pattern).
    from themis.nodes._llm import call_llm
    from themis.providers import build_model_string
    from themis.ui.live import LiveStatus

    strategy_model = cfg.chat_model or build_model_string(cfg)
    live = LiveStatus(mid, strategy_model)
    try:
        strategy_result = await call_llm(
            [{"role": "user", "content": (
                f"In ONE sentence (under 20 words), state the core legal strategy for: {brief[:300]}\n"
                f"Format: [document type] — [key legal basis/limitation/requirement]"
            )}],
            cfg,
            model_override=strategy_model,
        )
        await live.announce_strategy(strategy_result["content"].strip())
    except Exception:
        pass  # Strategy announcement is non-critical — never block the pipeline

    # T1-A: Pre-register the stream queue so draft.run() can push tokens to it.
    stream_q = register_draft_stream(mid)

    async def _consume_draft_tokens() -> None:
        live.begin_streaming()
        try:
            while True:
                token = await asyncio.wait_for(stream_q.get(), timeout=180)
                if token is None:
                    break
                live.stream_token(token)
        except asyncio.TimeoutError:
            pass

    consumer_task = asyncio.create_task(_consume_draft_tokens())

    try:
        async for chunk in graph.astream(
            state,
            config={"configurable": {"thread_id": mid}},
        ):
            for node_name, node_output in chunk.items():
                if not isinstance(node_output, dict):
                    continue
                state = {**state, **node_output}
                if node_name == "intake" and node_output.get("intake_complete"):
                    skill = node_output.get("active_skill_name") or ""
                    skill_label = f" [dim]({skill})[/dim]" if skill else ""
                    console.print(f"  [green]✓[/green] Intake{skill_label}")
                elif node_name == "research":
                    n = len(node_output.get("research_findings") or [])
                    console.print(f"  [green]✓[/green] Research — {n} case(s)")
                elif node_name == "cite":
                    g = len(node_output.get("grounded_citations") or [])
                    console.print(f"  [green]✓[/green] Citations — {g} grounded")
                elif node_name == "review":
                    console.print("  [green]✓[/green] Review")
    finally:
        unregister_draft_stream(mid)
        await consumer_task
        live.finish()

    if state.get("error"):
        return f"Error: {state['error']}"

    if not state.get("intake_complete"):
        questions = state.get("clarifying_questions") or []
        q_text = "\n".join(f"- {q}" for q in questions) if questions else "Please provide more details."
        return f"NEEDS_MORE_INFO matter_id={mid}\n{q_text}"

    draft = state.get("draft_output") or ""
    if not draft:
        return f"Draft not produced for matter {mid}. Try providing more detail."

    # Cache the draft so subsequent LLM calls for the same matter don't redraft.
    _DRAFT_CACHE[mid] = draft

    try:
        from themis.memory.session_store import init_db, save_session
        from themis.memory.matter_memory import save_matter_memory
        db_path = Path(cfg.sessions_db).expanduser()
        init_db(db_path)
        save_session(state, db_path)
        save_matter_memory(mid, state, Path(cfg.matters_dir).expanduser(), firm_id=cfg.default_firm_id)  # type: ignore[arg-type]
    except Exception:
        pass

    result_string = f"[Matter ID: {mid}]\n\n{draft}"

    matter_type = state.get("matter_type") or ""
    similar_note = ""
    try:
        from themis.memory.session_store import list_sessions
        all_matters = list_sessions(limit=20, sessions_db=cfg.sessions_db)
        similar = [
            m for m in all_matters
            if matter_type
            and matter_type.lower() in (m.get("matter_type") or "").lower()
            and m.get("matter_id") != mid
        ][:2]
        if similar:
            ids = ", ".join(f"{m.get('matter_id')} ({m.get('matter_type')})" for m in similar)
            similar_note = f"\n  • Cross-reference past matters: {ids}"
    except Exception:
        pass

    result_string += (
        "\n\n---\n"
        "**Draft ready.** Next steps:\n"
        "  • Say a filename to save as .docx\n"
        "  • Ask me to review risk annotations\n"
        "  • Ask me to check limitation"
        f"{similar_note}\n"
        "---"
    )
    return result_string


async def _tool_save_document(matter_id: str, filename: str, cfg: LexConfig) -> str:
    """Write the cached draft to ~/Downloads as a .docx file."""
    draft_text = _DRAFT_CACHE.get(matter_id, "")
    if not draft_text:
        # Try to find any cached draft if matter_id is missing/wrong
        if _DRAFT_CACHE:
            matter_id, draft_text = next(iter(_DRAFT_CACHE.items()))
        else:
            return "No draft found to save. Please generate a draft first."

    # Sanitise filename and ensure .docx extension
    safe_name = filename.strip().replace("/", "_").replace("\\", "_")
    if not safe_name:
        safe_name = f"Themis_Draft_{matter_id}.docx"
    if not safe_name.lower().endswith(".docx"):
        safe_name = safe_name.rsplit(".", 1)[0] + ".docx"

    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    output_path = downloads / safe_name

    try:
        from themis.tools.docx_writer import write_docx

        # Build a minimal state for the docx writer
        pseudo_state: dict = {
            "draft_output": draft_text,
            "matter_id": matter_id,
            "matter_type": "Legal Document",
            "parties": {},
            "jurisdiction": "",
            "plain_english_summary": None,
            "grounded_citations": None,
        }
        write_docx(pseudo_state, str(output_path))  # type: ignore[arg-type]
        return f"Saved to {output_path}"
    except Exception as e:
        # Fallback: plain text
        txt_path = output_path.with_suffix(".txt")
        txt_path.write_text(draft_text, encoding="utf-8")
        return f"Saved as plain text (docx error: {e}): {txt_path}"


async def _tool_research(query: str, cfg: LexConfig) -> str:
    from themis.graph import get_graph

    mid = f"M-{uuid.uuid4().hex[:8].upper()}"
    graph = get_graph(cfg)

    state: dict = {
        "user_input": query,
        "matter_id": mid,
        "intake_complete": False,
        "citations_verified": False,
        "research_only": True,
        "matter_type": "research",
        "parties": {"description": "N/A"},
        "jurisdiction": "India",
        "purpose": query,
        "messages": [{"role": "user", "content": query}],
    }

    async for chunk in graph.astream(
        state,
        config={"configurable": {"thread_id": mid}},
    ):
        for _, node_output in chunk.items():
            if isinstance(node_output, dict):
                state = {**state, **node_output}

    if state.get("error"):
        return f"Research error: {state['error']}"

    findings = state.get("research_findings") or []
    if not findings:
        return "No relevant case law found."

    lines = [f"Found {len(findings)} case(s):\n"]
    for f in findings:
        lines.append(f"• {f.get('case_name', '—')}  {f.get('citation', '')}")
        if f.get("relevance"):
            lines.append(f"  {f['relevance']}")

    statutes = state.get("statutes_cited") or []
    if statutes:
        lines.append(f"\nStatutes cited: {', '.join(statutes)}")

    return "\n".join(lines)


def _tool_list_matters(cfg: LexConfig) -> str:
    from themis.memory.matter_memory import list_matters

    matters = list_matters(Path(cfg.matters_dir).expanduser(), firm_id=cfg.default_firm_id)
    if not matters:
        return "No saved matters found."

    lines = [f"{len(matters)} matter(s) on file:\n"]
    for m in matters:
        lines.append(
            f"• {m['matter_id']}  {m.get('matter_type') or '—'}"
            f"  {m.get('parties') or ''}  [{m.get('last_modified', '')}]"
        )
    return "\n".join(lines)


def _tool_show_matter(matter_id: str, cfg: LexConfig) -> str:
    from themis.memory.matter_memory import load_matter_memory
    from themis.memory.session_store import get_session_state

    memory = load_matter_memory(matter_id, Path(cfg.matters_dir).expanduser(), firm_id=cfg.default_firm_id)
    if memory:
        return memory

    # Fall back to SQLite — chat-mode drafts save there, not to MEMORY.md on disk.
    state = get_session_state(matter_id, cfg.sessions_db)
    if not state:
        return f"Matter {matter_id} not found in memory or session history."

    parties = state.get("parties") or {}
    if isinstance(parties, dict):
        parties_str = "; ".join(f"{k}: {v}" for k, v in parties.items() if v)
    else:
        parties_str = str(parties)

    lines = [
        f"# Matter — {matter_id}",
        f"**Type:** {state.get('matter_type') or '—'}",
        f"**Parties:** {parties_str or '—'}",
        f"**Jurisdiction:** {state.get('jurisdiction') or '—'}",
        f"**Purpose:** {state.get('purpose') or '—'}",
    ]
    if state.get("plain_english_summary"):
        lines.append(f"\n**Summary:** {state['plain_english_summary']}")
    if state.get("statutes_cited"):
        lines.append(f"\n**Statutes cited:** {', '.join(state['statutes_cited'])}")
    if state.get("draft_output"):
        draft_preview = state["draft_output"][:500]
        lines.append(f"\n**Draft (preview):**\n{draft_preview}{'...' if len(state['draft_output']) > 500 else ''}")
    return "\n".join(lines)


def _tool_search_kb(query: str, cfg: LexConfig) -> str:
    from themis.tools.kb_query import search_kb

    db_path = Path(cfg.sessions_db).expanduser()
    results = search_kb(query, db_path)
    if not results:
        return "No matching research found in your knowledge base."

    lines = [f"{len(results)} result(s):\n"]
    for r in results[:5]:
        lines.append(f"• {r.get('case_name', '—')}  {r.get('citation', '')}")
        if r.get("relevance"):
            lines.append(f"  {r['relevance']}")
    return "\n".join(lines)
