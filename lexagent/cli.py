# WHY: rich is required for all output — never use print().
# Using rich gives the CLI a professional look that matches the product's positioning.
# It also makes it easy to render panels, spinners, tables, and markdown later
# without refactoring every print statement.

import asyncio
import uuid
from typing import Optional

import typer
from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import print as rprint

from lexagent.config import LexConfig
from lexagent.graph import get_graph
from lexagent.state import LexState

app = typer.Typer(
    name="lex",
    help="LexAgent — AI agent for lawyers. Global. Open-source. Self-improving.",
    add_completion=False,
)
# 'matter' is a sub-command group: `lex matter list`, `lex matter show <id>`
matter_app = typer.Typer(name="matter", help="Manage saved matters.")
app.add_typer(matter_app, name="matter")

console = Console()


@app.command()
def draft(
    brief: Optional[str] = typer.Argument(
        None,
        help='Matter brief, e.g. "I need an injunction for a property dispute in Delhi"',
    ),
    matter_id: Optional[str] = typer.Option(
        None,
        "--matter-id",
        "-m",
        help="Continue an existing matter by ID",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save draft to file (e.g. --output draft.docx). Phase 5 feature.",
    ),
) -> None:
    """
    Draft a legal document from a matter brief.

    If you don't provide a brief as an argument, you'll be prompted.
    LexAgent will ask clarifying questions, then produce a full draft.
    """
    cfg = LexConfig()

    # Phase 3: Enable LiteLLM disk cache (Layer 1 — all providers).
    # Must be called before any LLM call so the cache intercepts from the first request.
    from lexagent.nodes._llm import setup_litellm_cache
    setup_litellm_cache(cfg)

    # Phase 2: Warn on first run if SOUL.md has not been created.
    # WHY: A gentle nudge — not a hard block. The agent works without SOUL.md,
    # but the output will be generic rather than personalised.
    from lexagent.memory.soul import soul_path
    if not soul_path(cfg.home_dir).exists():
        console.print(
            "\n[yellow]Tip:[/yellow] You haven't set up your lawyer profile yet. "
            "Run [bold cyan]lex setup[/bold cyan] for personalised drafts.\n"
        )

    if not brief:
        brief = Prompt.ask(
            "[bold cyan]Describe your matter[/bold cyan]",
            console=console,
        )

    if not brief.strip():
        console.print("[red]No matter brief provided. Exiting.[/red]")
        raise typer.Exit(1)

    # Phase 5: pass output path into the graph via state so the review node
    # can call docx_writer after validation completes.
    output_path: str | None = output

    # Generate a matter ID for this session, or reuse the one passed in
    session_matter_id = matter_id or f"M-{uuid.uuid4().hex[:8].upper()}"

    # Phase 2: If continuing an existing matter, load the previous state snapshot
    prior_state: Optional[dict] = None
    if matter_id:
        from lexagent.memory.session_store import get_session_state
        prior_state = get_session_state(matter_id, cfg.sessions_db)
        if prior_state:
            console.print(f"\n[cyan]Resuming matter {matter_id}...[/cyan]")
        else:
            console.print(f"\n[yellow]No saved session found for {matter_id}. Starting fresh.[/yellow]")

    console.print()
    console.print(
        Panel(
            f"[bold]Matter ID:[/bold] {session_matter_id}\n"
            f"[bold]Brief:[/bold] {brief}",
            title="[bold cyan]⚖ LexAgent[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()

    # Run the graph, handling the interactive intake loop
    asyncio.run(_run_draft(brief, session_matter_id, cfg, prior_state, output_path))


async def _run_draft(
    initial_brief: str,
    matter_id: str,
    cfg: LexConfig,
    prior_state: Optional[dict] = None,
    output_path: Optional[str] = None,
) -> None:
    """
    Runs the LangGraph draft workflow interactively.

    The intake node may loop multiple times asking clarifying questions.
    Each time it does, we print the questions and collect the lawyer's answers
    before invoking the graph again with the updated state.
    After the graph completes, the session is saved to SQLite and MEMORY.md.
    """
    from lexagent.memory.matter_memory import save_matter_memory
    from lexagent.memory.session_store import init_db, save_session

    graph = get_graph()

    # Initial state — if we have a prior state snapshot, use it as the base.
    # WHY: This is how `lex draft --matter-id M001` continues a matter.
    # We overlay the new brief on top of the prior state so the agent knows
    # the context (parties, jurisdiction, etc.) from the last session.
    if prior_state:
        state: LexState = {**prior_state}  # type: ignore[assignment]
        state["user_input"] = initial_brief
        state["intake_complete"] = False
        state["draft_output"] = None
        state["plain_english_summary"] = None
        state["messages"] = [HumanMessage(content=initial_brief)]
        state["grounded_citations"] = None
        state["retrieval_chunks"] = None
        state["docx_path"] = output_path
    else:
        state = _blank_state(initial_brief, matter_id, output_path)

    # WHY: We use astream() to process the graph node by node.
    # LANGGRAPH: astream() is an async generator that yields the state update
    # from each node as it completes. This lets us show progress and handle
    # the interactive intake loop without waiting for the full graph to finish.
    max_intake_rounds = 5  # Safety limit — prevents infinite loops
    intake_round = 0

    while True:
        intake_round += 1
        if intake_round > max_intake_rounds:
            console.print("[red]Too many intake rounds. Please start over with more detail.[/red]")
            break

        with console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
            # Stream through one pass of the graph
            final_state = state
            async for chunk in graph.astream(state):
                # chunk is {node_name: partial_state_dict}
                for node_name, node_output in chunk.items():
                    if isinstance(node_output, dict):
                        # Merge the node's output into our local state copy
                        final_state = {**final_state, **node_output}

        state = final_state

        # Check for errors first
        if state.get("error"):
            console.print(f"\n[bold red]Error:[/bold red] {state['error']}")
            break

        # If intake is not complete, print questions and get lawyer's answers
        if not state.get("intake_complete"):
            questions = state.get("clarifying_questions") or []
            if questions:
                console.print()
                console.print(Panel(
                    "\n".join(f"[bold cyan]{i+1}.[/bold cyan] {q}" for i, q in enumerate(questions)),
                    title="[bold yellow]LexAgent needs a few more details[/bold yellow]",
                    border_style="yellow",
                ))
                console.print()

                answers = Prompt.ask(
                    "[bold]Your answers[/bold] (answer all questions above, separated by commas or in full sentences)",
                    console=console,
                )

                # Add the answers to the message history and update user_input
                state = {
                    **state,
                    "user_input": f"{state['user_input']}\n\nAnswers to your questions: {answers}",
                    "messages": list(state.get("messages", [])) + [HumanMessage(content=answers)],
                }
                continue  # Loop — run the graph again with updated state

        # Intake is complete — the draft should now be in state
        if state.get("draft_output"):
            _render_draft(state)

            # Phase 2: Persist the session and matter memory
            if cfg.auto_save_matter:
                _save_session_and_memory(state, cfg)

            break

        # Shouldn't reach here, but safety exit
        console.print("[yellow]No draft was produced. Try again with more detail.[/yellow]")
        break


def _blank_state(brief: str, matter_id: str, output_path: Optional[str] = None) -> LexState:
    """Create a fresh initial state for a new matter session."""
    return {  # type: ignore[return-value]
        "user_input": brief,
        "matter_id": matter_id,
        "intake_complete": False,
        "citations_verified": False,
        "messages": [HumanMessage(content=brief)],
        "matter_type": None,
        "parties": None,
        "jurisdiction": None,
        "jurisdiction_country": None,
        "purpose": None,
        "key_clauses": None,
        "tone_preference": None,
        "risks_to_address": None,
        "citations_required": None,
        "clarifying_questions": None,
        "research_findings": None,
        "statutes_cited": None,
        "limitation_analysis": None,
        "document_outline": None,
        "draft_output": None,
        "risk_annotations": None,
        "plain_english_summary": None,
        "unverified_citations": None,
        "lawyer_soul": None,
        "active_skill": None,
        "error": None,
        "next_node": None,
        # Phase 5
        "grounded_citations": None,
        "retrieval_chunks": None,
        "docx_path": output_path,
    }


def _save_session_and_memory(state: LexState, cfg: LexConfig) -> None:
    """
    Persist the completed session to SQLite and MEMORY.md.
    Called after a successful draft. Errors are caught so a save failure
    never crashes the CLI — the lawyer already has their draft on screen.
    """
    from lexagent.memory.matter_memory import save_matter_memory
    from lexagent.memory.session_store import init_db, save_session

    try:
        init_db(cfg.sessions_db)
        session_id = save_session(state, cfg.sessions_db)
        mem_path = save_matter_memory(
            state.get("matter_id") or "unknown",
            state,
            cfg.matters_dir,
        )
        console.print(
            f"\n[dim]✓ Session saved (ID: {session_id}) | "
            f"Matter memory: {mem_path}[/dim]"
        )
    except Exception as e:
        console.print(f"\n[dim yellow]Note: Could not save session — {e}[/dim yellow]")


def _render_draft(state: LexState) -> None:
    """Render the completed draft in the terminal using rich panels."""
    console.print()
    console.print(
        Panel(
            Markdown(state["draft_output"]),
            title="[bold green]⚖ Draft Complete[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )

    if state.get("plain_english_summary"):
        console.print()
        console.print(
            Panel(
                state["plain_english_summary"],
                title="[bold blue]Plain English Summary[/bold blue]",
                border_style="blue",
            )
        )

    if state.get("unverified_citations"):
        console.print()
        console.print(
            Panel(
                "\n".join(f"• {c}" for c in state["unverified_citations"]),
                title="[bold red]⚠ Unverified Citations — Human Review Required[/bold red]",
                border_style="red",
            )
        )

    # Phase 2: Show the lawyer's name in the footer if SOUL.md is loaded
    soul = state.get("lawyer_soul")
    lawyer_name = ""
    if isinstance(soul, dict):
        lawyer_name = soul.get("name", "")

    if state.get("docx_path"):
        console.print()
        console.print(
            Panel(
                f"[bold]Saved:[/bold] {state['docx_path']}",
                title="[bold green]📄 .docx Export[/bold green]",
                border_style="green",
            )
        )

    grounded = state.get("grounded_citations") or []
    if grounded:
        verified_count = sum(1 for g in grounded if g.get("verified"))
        console.print()
        console.print(f"[dim]Citations: {verified_count}/{len(grounded)} grounded to source chunks[/dim]")

    footer_parts = [f"Matter ID: {state.get('matter_id')}"]
    if lawyer_name:
        footer_parts.append(f"Lawyer: {lawyer_name}")
    footer_parts.append("Phase 5 — hybrid retrieval · chunk-level grounding · .docx output")

    console.print()
    console.print(f"[dim]{' | '.join(footer_parts)}[/dim]")


# -----------------------------------------------------------------------
# lex setup
# -----------------------------------------------------------------------

@app.command()
def setup() -> None:
    """
    First-run setup wizard — creates your lawyer profile (SOUL.md).
    Run this once before your first draft for personalised output.
    """
    from lexagent.memory.soul import run_setup_wizard, soul_path
    from lexagent.memory.session_store import init_db

    cfg = LexConfig()

    existing = soul_path(cfg.home_dir)
    if existing.exists():
        overwrite = Prompt.ask(
            f"[yellow]Profile already exists at {existing}.[/yellow] Overwrite?",
            choices=["y", "n"],
            default="n",
            console=console,
        )
        if overwrite.lower() != "y":
            console.print("[dim]Setup cancelled. Your existing profile is unchanged.[/dim]")
            raise typer.Exit(0)

    run_setup_wizard(cfg.home_dir)

    # Initialise the SQLite sessions database on first setup
    try:
        init_db(cfg.sessions_db)
        console.print(f"[dim]Sessions database ready at {cfg.sessions_db}[/dim]")
    except Exception as e:
        console.print(f"[dim yellow]Could not initialise sessions DB: {e}[/dim yellow]")


# -----------------------------------------------------------------------
# lex config
# -----------------------------------------------------------------------

@app.command()
def config() -> None:
    """Show current LexAgent configuration."""
    cfg = LexConfig()
    console.print()
    console.print(Panel(
        f"[bold]Model:[/bold] {cfg.model_provider}/{cfg.default_model}\n"
        f"[bold]Kanoon backend:[/bold] {cfg.kanoon_backend}\n"
        f"[bold]eCourts backend:[/bold] {cfg.ecourts_backend}\n"
        f"[bold]Home dir:[/bold] {cfg.home_dir}\n"
        f"[bold]Auto-verify citations:[/bold] {cfg.auto_verify_citations}\n"
        f"[bold]Auto-save matter:[/bold] {cfg.auto_save_matter}",
        title="[bold cyan]LexAgent Config[/bold cyan]",
        border_style="cyan",
    ))


# -----------------------------------------------------------------------
# lex matter list / lex matter show
# -----------------------------------------------------------------------

@matter_app.command("list")
def matter_list() -> None:
    """List all saved matters, most recent first."""
    from lexagent.memory.matter_memory import list_matters

    cfg = LexConfig()
    matters = list_matters(cfg.matters_dir)

    if not matters:
        console.print("[yellow]No matters saved yet. Run [bold]lex draft[/bold] to create your first.[/yellow]")
        raise typer.Exit(0)

    table = Table(
        title="Saved Matters",
        border_style="cyan",
        show_lines=True,
    )
    table.add_column("Matter ID", style="bold cyan")
    table.add_column("Last Modified")
    table.add_column("Type")
    table.add_column("Parties")

    for m in matters:
        table.add_row(
            m["matter_id"],
            m["last_modified"],
            m["matter_type"] or "—",
            m["parties"] or "—",
        )

    console.print()
    console.print(table)
    console.print(f"\n[dim]Run [bold]lex matter show <MATTER-ID>[/bold] to view details.[/dim]")


@matter_app.command("show")
def matter_show(matter_id: str = typer.Argument(..., help="Matter ID to display")) -> None:
    """Show the memory log for a specific matter."""
    from lexagent.memory.matter_memory import load_matter_memory

    cfg = LexConfig()
    memory = load_matter_memory(matter_id, cfg.matters_dir)

    if not memory:
        console.print(f"[red]No memory found for matter {matter_id}.[/red]")
        raise typer.Exit(1)

    console.print()
    console.print(Panel(
        Markdown(memory),
        title=f"[bold cyan]Matter Memory — {matter_id}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))


# -----------------------------------------------------------------------
# lex search
# -----------------------------------------------------------------------

@app.command()
def search(query: str = typer.Argument(..., help="Full-text search query across all past matters")) -> None:
    """Search all past matters by keyword."""
    from lexagent.memory.session_store import search_sessions

    cfg = LexConfig()

    try:
        results = search_sessions(query, limit=10, sessions_db=cfg.sessions_db)
    except Exception as e:
        console.print(f"[red]Search failed: {e}[/red]")
        raise typer.Exit(1)

    if not results:
        console.print(f"[yellow]No sessions found matching '{query}'.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"Search results for: {query}", border_style="cyan", show_lines=True)
    table.add_column("Matter ID", style="bold cyan")
    table.add_column("Date")
    table.add_column("Type")
    table.add_column("Parties")
    table.add_column("Summary")

    for r in results:
        table.add_row(
            r.get("matter_id", ""),
            r.get("created_at", "")[:10],
            r.get("matter_type", "") or "—",
            r.get("parties", "") or "—",
            (r.get("summary", "") or "—")[:60],
        )

    console.print()
    console.print(table)


# -----------------------------------------------------------------------
# lex reminder add / list / delete
# -----------------------------------------------------------------------

reminder_app = typer.Typer(name="reminder", help="Manage hearing reminders.")
app.add_typer(reminder_app, name="reminder")


@reminder_app.command("add")
def reminder_add(
    matter_id: str = typer.Option(..., "--matter-id", "-m", help="Matter ID (e.g. M-ABCD1234)"),
    date: str = typer.Option(..., "--date", "-d", help="Hearing date in YYYY-MM-DD format"),
    note: str = typer.Option("", "--note", "-n", help="Short note (e.g. 'HC hearing — injunction')"),
    days_before: int = typer.Option(1, "--days-before", help="Fire reminder N days before the hearing"),
) -> None:
    """
    Set a hearing reminder for a matter.

    Example:
      lex reminder add --matter-id M001 --date 2026-08-15 --note "HC hearing"
    """
    from lexagent.memory.session_store import add_reminder

    cfg = LexConfig()
    rid = add_reminder(
        matter_id=matter_id,
        hearing_date=date,
        note=note,
        days_before=days_before,
        sessions_db=cfg.sessions_db,
    )
    console.print(
        Panel(
            f"[bold]Reminder ID:[/bold] {rid}\n"
            f"[bold]Matter:[/bold] {matter_id}\n"
            f"[bold]Hearing date:[/bold] {date}\n"
            f"[bold]Fires:[/bold] {days_before} day(s) before\n"
            f"[bold]Note:[/bold] {note or '—'}",
            title="[bold green]✅ Reminder set[/bold green]",
            border_style="green",
        )
    )


@reminder_app.command("list")
def reminder_list(
    matter_id: Optional[str] = typer.Option(None, "--matter-id", "-m", help="Filter by matter ID"),
    all_: bool = typer.Option(False, "--all", "-a", help="Include already-fired reminders"),
) -> None:
    """List pending hearing reminders."""
    from lexagent.memory.session_store import list_reminders

    cfg = LexConfig()
    reminders = list_reminders(matter_id=matter_id, include_fired=all_, sessions_db=cfg.sessions_db)

    if not reminders:
        console.print("[yellow]No pending reminders. Use [bold]lex reminder add[/bold] to set one.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Hearing Reminders", border_style="cyan", show_lines=True)
    table.add_column("ID", style="dim")
    table.add_column("Matter ID", style="bold cyan")
    table.add_column("Hearing Date")
    table.add_column("Fire At")
    table.add_column("Note")
    table.add_column("Fired", style="dim")

    for r in reminders:
        table.add_row(
            str(r["id"]),
            r["matter_id"],
            r["hearing_date"],
            r["fire_at"][:16],
            r.get("note") or "—",
            "✓" if r["fired"] else "—",
        )

    console.print()
    console.print(table)


@reminder_app.command("delete")
def reminder_delete(
    reminder_id: int = typer.Argument(..., help="Reminder ID to delete (see lex reminder list)"),
) -> None:
    """Delete a reminder by ID."""
    from lexagent.memory.session_store import delete_reminder

    cfg = LexConfig()
    deleted = delete_reminder(reminder_id, sessions_db=cfg.sessions_db)
    if deleted:
        console.print(f"[green]✓ Reminder {reminder_id} deleted.[/green]")
    else:
        console.print(f"[red]No reminder found with ID {reminder_id}.[/red]")
        raise typer.Exit(1)


@app.command()
def gateway(
    service: str = typer.Argument(
        "telegram",
        help="Gateway service to start. Currently supported: telegram",
    ),
) -> None:
    """
    Start a messaging gateway for LexAgent.

    Examples:
      lex gateway telegram   — start the Telegram bot (long-polling)
    """
    cfg = LexConfig()

    if service.lower() == "telegram":
        from lexagent.gateway.telegram import run_telegram_bot
        run_telegram_bot(cfg)
    elif service.lower() in ("web", "api", "control-plane", "server"):
        import uvicorn
        from lexagent.gateway.control_plane import app as fastapi_app
        console.print(f"[bold cyan]⚖ LexAgent Control Plane[/bold cyan] — http://{cfg.control_plane_host}:{cfg.control_plane_port}")
        uvicorn.run(fastapi_app, host=cfg.control_plane_host, port=cfg.control_plane_port)
    else:
        console.print(f"[red]Unknown gateway service: {service}[/red]")
        console.print("Supported: telegram, web")
        raise typer.Exit(1)


@app.command()
def voice(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind the voice server"),
    port: int = typer.Option(8001, "--port", "-p", help="Port for the voice gateway server"),
    twilio: bool = typer.Option(False, "--twilio", help="Print Twilio webhook setup instructions"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (development)"),
) -> None:
    """
    Start the LexAgent Voice AI gateway server.

    Opens a browser-based voice interface at http://localhost:<port>/voice/client
    and a WebSocket endpoint at ws://localhost:<port>/voice/ws/<session-id>.

    Optionally registers Twilio webhooks for phone call support.

    Examples:
      lex voice                 — start on port 8001
      lex voice --port 9000     — custom port
      lex voice --twilio        — show Twilio webhook instructions
    """
    import uvicorn
    from lexagent.gateway.control_plane import app as fastapi_app

    cfg = LexConfig()

    console.print()
    console.print(
        Panel(
            f"[bold]Voice gateway:[/bold] http://{host}:{port}/voice/client\n"
            f"[bold]WebSocket:[/bold] ws://{host}:{port}/voice/ws/<session-id>\n"
            f"[bold]STT backend:[/bold] {getattr(cfg, 'stt_backend', 'stub')}\n"
            f"[bold]TTS backend:[/bold] {getattr(cfg, 'tts_backend', 'stub')}\n"
            f"[bold]Voice health:[/bold] http://{host}:{port}/voice/health\n\n"
            "[dim]Open the client URL in your browser to start dictating.[/dim]",
            title="[bold cyan]⚖ LexAgent Voice Gateway[/bold cyan]",
            border_style="cyan",
        )
    )

    if twilio:
        twilio_sid  = getattr(cfg, 'twilio_account_sid', None)
        twilio_num  = getattr(cfg, 'twilio_phone_number', None)
        console.print(
            Panel(
                f"[bold]Twilio Account SID:[/bold] {twilio_sid or '[red]NOT SET[/red]'}\n"
                f"[bold]Twilio Phone Number:[/bold] {twilio_num or '[red]NOT SET[/red]'}\n\n"
                f"[bold]Incoming call webhook:[/bold] https://YOUR-DOMAIN/voice/incoming\n"
                f"[bold]Gather webhook:[/bold] https://YOUR-DOMAIN/voice/gather\n\n"
                "[dim]Use ngrok to expose locally: ngrok http {port}[/dim]\n"
                "[dim]Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER in .env[/dim]",
                title="[bold yellow]📞 Twilio Phone Gateway Setup[/bold yellow]",
                border_style="yellow",
            )
        )

    console.print(f"\n[dim]Starting server on {host}:{port}... (Ctrl+C to stop)[/dim]\n")
    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    app()
