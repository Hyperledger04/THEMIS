# WHY: rich is required for all output — never use print().
# Using rich gives the CLI a professional look that matches the product's positioning.
# It also makes it easy to render panels, spinners, tables, and markdown later
# without refactoring every print statement.

import asyncio
import uuid
from pathlib import Path
from typing import List, Optional

import typer
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import print as rprint

from themis.config import LexConfig
from themis.graph import get_graph
from themis.state import SeniorCounselState
from themis.ui.spinner import LexAnimator


def _compress_paste_display(console: Console, text: str) -> None:
    """
    Replace echoed multi-line paste with a compact summary line.
    Triggered when text has >1 line or >120 chars — threshold that catches pastes
    but not normal typed answers.
    WHY: Rich can't suppress terminal echo during Prompt.ask(), but we can
    overwrite the echoed lines immediately after the call returns by moving
    the cursor up and clearing to end of screen.
    """
    line_count = text.count("\n") + 1
    char_count = len(text)
    if line_count > 1 or char_count > 120:
        # ANSI: move cursor up line_count lines, then clear from cursor to end of screen
        console.print(f"\x1b[{line_count}A\x1b[J", end="")
        console.print(f"[dim][pasted {line_count} line{'s' if line_count > 1 else ''} · {char_count} chars][/dim]")

def _default_to_chat(ctx: typer.Context) -> None:
    """If 'lex' is invoked with no subcommand, start the chat interface."""
    if ctx.invoked_subcommand is None:
        cfg = LexConfig()
        from themis.nodes._llm import setup_litellm_cache
        setup_litellm_cache(cfg)
        from themis.chat import run_chat
        asyncio.run(run_chat(cfg))


app = typer.Typer(
    name="lex",
    help="Themis — AI agent for lawyers. Global. Open-source. Self-improving.",
    add_completion=False,
    invoke_without_command=True,
    callback=_default_to_chat,
)
matter_app = typer.Typer(name="matter", help="Manage saved matters.")
app.add_typer(matter_app, name="matter")

agent_app = typer.Typer(name="agent", help="Create and manage custom agent personas.")
app.add_typer(agent_app, name="agent")

console = Console()


# ---------------------------------------------------------------------------
# lex chat
# ---------------------------------------------------------------------------


@app.command()
def chat() -> None:
    """Chat with Themis in natural language — draft, research, manage matters."""
    cfg = LexConfig()
    from themis.nodes._llm import setup_litellm_cache
    setup_litellm_cache(cfg)
    from themis.chat import run_chat
    asyncio.run(run_chat(cfg))


# ---------------------------------------------------------------------------
# lex draft
# ---------------------------------------------------------------------------

@app.command()
def draft(
    brief: Optional[str] = typer.Argument(
        None,
        help='Matter brief. Use @agentname at the start to invoke a specific agent.',
    ),
    matter_id: Optional[str] = typer.Option(
        None, "--matter-id", "-m", help="Continue an existing matter by ID",
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Save draft to .docx file (e.g. --output draft.docx)",
    ),
    agent: Optional[str] = typer.Option(
        None, "--agent", "-a", help="Agent persona to use (e.g. --agent vikram or --agent @vikram)",
    ),
    skill: Optional[List[str]] = typer.Option(
        None,
        "--skill",
        "-S",
        help="Force-load a skill by name (repeatable: --skill s138_complaint --skill bail_application)",
    ),
    redline: Optional[str] = typer.Option(
        None, "--redline", "-R",
        help="Path to original .docx to produce tracked-changes redline against new draft.",
    ),
    chamber: bool = typer.Option(
        False, "--chamber", "-C",
        help="Enable adversarial multi-agent review chamber before final output.",
    ),
) -> None:
    """
    Draft a legal document from a matter brief.

    Use @agentname in your brief to invoke a specific agent persona:
      lex draft "@vikram I need an injunction for a property dispute in Delhi"
      lex draft --agent priya "draft a settlement agreement"
    """
    cfg = LexConfig()

    from themis.nodes._llm import setup_litellm_cache
    setup_litellm_cache(cfg)

    from themis.memory.soul import soul_path
    if not soul_path(cfg.home_dir).exists():
        console.print(
            "\n[yellow]Tip:[/yellow] You haven't set up your lawyer profile yet. "
            "Run [bold cyan]lex setup[/bold cyan] for personalised drafts.\n"
        )

    # Nudge if no research tools are configured — non-blocking, draft still runs
    _has_research = any([
        cfg.enable_kanoon,
        cfg.tavily_enabled,
        cfg.playwright_enabled,
        cfg.web_search_enabled,
        cfg.jina_enabled,
        cfg.ecourts_backend != "stub",
        cfg.serpapi_enabled,
        cfg.perplexity_enabled,
        cfg.firecrawl_enabled,
        cfg.legislation_enabled,
    ])
    if not _has_research:
        console.print(
            "\n[yellow]⚠  No research tools configured.[/yellow] "
            "Run [bold cyan]lex config tools[/bold cyan] to enable Indian Kanoon, Tavily, eCourts, or other sources.\n"
        )

    if not brief:
        brief = Prompt.ask(
            "[bold cyan]Describe your matter[/bold cyan] [dim](or start with @agentname)[/dim]",
            console=console,
        )
        _compress_paste_display(console, brief)

    if not brief.strip():
        console.print("[red]No matter brief provided. Exiting.[/red]")
        raise typer.Exit(1)

    # --- Parse @agent from brief ---
    from themis.agents.registry import parse_agent_mention, load_agent
    agent_id: Optional[str] = None
    agent_config: Optional[dict] = None

    # Priority: --agent flag > @mention in brief
    if agent:
        agent_id = agent.lstrip("@").lower()
    else:
        agent_id_from_brief, brief = parse_agent_mention(brief)
        if agent_id_from_brief:
            agent_id = agent_id_from_brief

    if agent_id:
        agent_config = load_agent(agent_id, cfg.agents_dir)
        if not agent_config:
            console.print(
                f"[yellow]Agent [bold]@{agent_id}[/bold] not found. "
                "Run [bold cyan]lex agent list[/bold cyan] to see available agents. "
                "Continuing without an agent persona.[/yellow]\n"
            )
            agent_id = None

    if not brief.strip() and agent_id:
        brief = Prompt.ask(
            f"[bold cyan]Matter brief for @{agent_id}[/bold cyan]",
            console=console,
        )

    output_path: str | None = output
    session_matter_id = matter_id or f"M-{uuid.uuid4().hex[:8].upper()}"

    prior_state: Optional[dict] = None
    if matter_id:
        from themis.memory.session_store import get_session_state
        prior_state = get_session_state(matter_id, cfg.sessions_db)
        if prior_state:
            console.print(f"\n[cyan]Resuming matter {matter_id}...[/cyan]")
        else:
            console.print(f"\n[yellow]No saved session found for {matter_id}. Starting fresh.[/yellow]")

    console.print()

    # --- Header panel ---
    header_lines = [
        f"[bold]Matter ID:[/bold] {session_matter_id}",
        f"[bold]Brief:[/bold] {brief}",
    ]
    if agent_config:
        from themis.agents.faces import FACES
        face = FACES.get(agent_config.get("face", ""), {})
        header_lines.append(
            f"[bold]Agent:[/bold] [cyan]@{agent_config['id']}[/cyan] — "
            f"{agent_config.get('name', '')}  [dim]{agent_config.get('tagline', '')}[/dim]"
        )

    console.print(
        Panel(
            "\n".join(header_lines),
            title="[bold cyan]⚖ Themis[/bold cyan]",
            border_style="cyan",
        )
    )

    # Show agent face if active
    if agent_config:
        from themis.agents.faces import FACES
        face = FACES.get(agent_config.get("face", "sharp_counsel"), FACES["sharp_counsel"])
        console.print(
            Panel(
                f"[bold cyan]{face['art']}[/bold cyan]",
                title=f"[dim]@{agent_config['id']}[/dim]",
                border_style="dim cyan",
                padding=(0, 2),
                width=22,
            )
        )

    console.print()

    asyncio.run(_run_draft(brief, session_matter_id, cfg, prior_state, output_path, agent_config, list(skill) if skill else None, redline_source_path=redline, chamber_enabled=chamber))


# ---------------------------------------------------------------------------
# Node → phase mapping for the animated spinner
# ---------------------------------------------------------------------------

_NODE_PHASE: dict[str, str] = {
    "intake":          "intake",
    "research":        "research",
    "draft":           "draft",
    "cite":            "cite",
    "review":          "review",
    "contract_review": "review",
}

_NODE_NEXT_LABEL: dict[str, str] = {
    "intake":          "[bold cyan]Searching Indian case law...[/bold cyan]",
    "research":        "[bold cyan]Drafting document...[/bold cyan]",
    "draft":           "[bold cyan]Verifying citations...[/bold cyan]",
    "cite":            "[bold cyan]Running final review...[/bold cyan]",
    "review":          "[bold cyan]Done.[/bold cyan]",
    "contract_review": "[bold cyan]Done.[/bold cyan]",
}


def _print_node_done(status, anim: LexAnimator, node_name: str, node_output: dict) -> None:
    """
    Print a one-line completion summary for a finished node and advance
    the spinner phase to describe what comes next.
    """
    if node_name == "intake":
        mt = node_output.get("matter_type") or "—"
        juris = node_output.get("jurisdiction") or "—"
        parties = node_output.get("parties") or {}
        p_str = ""
        if isinstance(parties, dict) and parties:
            p_str = " · ".join(f"{v}" for v in list(parties.values())[:2])
        detail = mt
        if juris != "—":
            detail += f"  ·  {juris}"
        if p_str:
            detail += f"  ·  {p_str}"
        console.print(f"[green]✓[/green] [bold]Intake[/bold]  {detail}")

        if node_output.get("intake_complete"):
            anim.set_phase("research")
            status.update(_NODE_NEXT_LABEL["intake"])
        else:
            anim.set_phase("intake")
            status.update("[bold yellow]Waiting for your answers...[/bold yellow]")

    elif node_name == "research":
        findings = node_output.get("research_findings") or []
        statutes = node_output.get("statutes_cited") or []
        limitation = "  ·  limitation checked" if node_output.get("limitation_analysis") else ""
        console.print(
            f"[green]✓[/green] [bold]Research[/bold]  "
            f"{len(findings)} case(s) · {len(statutes)} statute(s){limitation}"
        )
        anim.set_phase("draft")
        status.update(_NODE_NEXT_LABEL["research"])

    elif node_name == "draft":
        draft_text = node_output.get("draft_output") or ""
        words = len(draft_text.split()) if draft_text else 0
        console.print(f"[green]✓[/green] [bold]Draft[/bold]  {words:,} words")
        anim.set_phase("cite")
        status.update(_NODE_NEXT_LABEL["draft"])

    elif node_name == "cite":
        grounded = node_output.get("grounded_citations") or []
        unverified = node_output.get("unverified_citations") or []
        flag = f"  ·  [yellow]{len(unverified)} flagged for review[/yellow]" if unverified else ""
        console.print(
            f"[green]✓[/green] [bold]Citations[/bold]  {len(grounded)} grounded{flag}"
        )
        anim.set_phase("review")
        status.update(_NODE_NEXT_LABEL["cite"])

    elif node_name == "review":
        docx = node_output.get("docx_path")
        extra = f"  ·  .docx → {docx}" if docx else ""
        console.print(f"[green]✓[/green] [bold]Review[/bold]{extra}")

    elif node_name == "retrieve":
        chunks = node_output.get("retrieval_chunks") or []
        console.print(f"[green]✓[/green] [bold]Retrieved[/bold]  {len(chunks)} context chunk(s)")
        anim.set_phase("draft")
        status.update(_NODE_NEXT_LABEL["research"])

    elif node_name == "contract_review":
        console.print("[green]✓[/green] [bold]Contract Review[/bold]  risk analysis complete")

    else:
        console.print(f"[green]✓[/green] [dim]{node_name}[/dim]")


async def _run_draft(
    initial_brief: str,
    matter_id: str,
    cfg: LexConfig,
    prior_state: Optional[dict] = None,
    output_path: Optional[str] = None,
    agent_config: Optional[dict] = None,
    forced_skill_names: Optional[List[str]] = None,
    redline_source_path: Optional[str] = None,
    chamber_enabled: bool = False,
) -> None:
    from themis.nodes.draft import register_draft_stream, unregister_draft_stream

    graph = get_graph()

    if prior_state:
        state: SeniorCounselState = {**prior_state}  # type: ignore[assignment]
        state["user_input"] = initial_brief
        state["intake_complete"] = False
        state["draft_output"] = None
        state["plain_english_summary"] = None
        state["messages"] = [{"role": "user", "content": initial_brief}]
        state["grounded_citations"] = None
        state["retrieval_chunks"] = None
        state["docx_path"] = output_path
        state["active_agent"] = agent_config
        state["forced_skill_names"] = forced_skill_names  # type: ignore[typeddict-unknown-key]
        state["redline_source_path"] = redline_source_path  # type: ignore[typeddict-unknown-key]
        state["chamber_enabled"] = chamber_enabled  # type: ignore[typeddict-unknown-key]
    else:
        state = _blank_state(initial_brief, matter_id, output_path, agent_config, forced_skill_names, redline_source_path, chamber_enabled=chamber_enabled)

    max_intake_rounds = 5
    intake_round = 0
    _GRAPH_TIMEOUT = 180

    # WHY: Register once before the loop — the draft node pushes tokens here.
    # The queue persists across intake rounds; only the draft node populates it,
    # so it stays empty until intake is complete and drafting begins.
    draft_q = register_draft_stream(matter_id)

    try:
        while True:
            intake_round += 1
            if intake_round > max_intake_rounds:
                console.print("[red]Too many intake rounds. Please start over with more detail.[/red]")
                break

            final_state = state
            stream_task: Optional[asyncio.Task] = None

            # WHY: LexAnimator runs as a background asyncio task that cycles funny phrases
            # while each node executes. It is stopped and restarted between graph passes
            # so the phase always matches the current work.
            with console.status("[bold cyan]⚖  analyzing your brief...[/bold cyan]", spinner="dots") as status:
                anim = LexAnimator(status, phase="starting")
                anim.start()

                # WHY: _consume_tokens runs as a concurrent asyncio task alongside
                # graph.astream(). While the LLM streams tokens into draft_q, this task
                # reads them and prints immediately — giving live character-by-character output.
                # On the first token it stops the spinner (status.stop is idempotent) so
                # streaming text appears cleanly without the spinner line interfering.
                async def _consume_tokens(q: asyncio.Queue, s=status, a=anim) -> None:
                    seen_first = False
                    while True:
                        token = await q.get()
                        if token is None:
                            break
                        if not seen_first:
                            a.stop()
                            s.stop()
                            console.print()
                            seen_first = True
                        console.print(token, end="", highlight=False)
                    if seen_first:
                        console.print()  # trailing newline after last token

                stream_task = asyncio.create_task(_consume_tokens(draft_q))

                try:
                    async with asyncio.timeout(_GRAPH_TIMEOUT):
                        async for chunk in graph.astream(
                            state,
                            config={"configurable": {"thread_id": state["matter_id"]}},
                        ):
                            for node_name, node_output in chunk.items():
                                if isinstance(node_output, dict):
                                    final_state = {**final_state, **node_output}
                                    _print_node_done(status, anim, node_name, node_output)

                except asyncio.TimeoutError:
                    anim.stop()
                    console.print(
                        f"\n[bold red]⏱ Timed out after {_GRAPH_TIMEOUT}s.[/bold red]\n"
                        "Common causes:\n"
                        "  • Wrong model name in LEX_MODEL — check your .env\n"
                        "  • Expired or invalid API key\n"
                        "  • Network connectivity issue\n"
                        f"\n[dim]Current model: {cfg.model_provider}/{cfg.default_model}[/dim]\n"
                        "[dim]Run [bold]lex config[/bold] to inspect settings.[/dim]"
                    )
                    if stream_task and not stream_task.done():
                        stream_task.cancel()
                    return

                except Exception as exc:
                    anim.stop()
                    console.print(f"\n[bold red]Graph error:[/bold red] {exc}")
                    if stream_task and not stream_task.done():
                        stream_task.cancel()
                    return

                finally:
                    anim.stop()

            # Settle the stream task: await it if the draft node ran (sent sentinel),
            # or cancel it if this was an intake-only round (no sentinel was sent).
            if stream_task:
                if not stream_task.done():
                    stream_task.cancel()
                try:
                    await stream_task
                except asyncio.CancelledError:
                    pass

            state = final_state

            if state.get("error"):
                console.print(f"\n[bold red]Error:[/bold red] {state['error']}")
                break

            if not state.get("intake_complete"):
                questions = state.get("clarifying_questions") or []
                if questions:
                    # Autonomous mode: skip questions when brief contains the 4 core fields.
                    # WHY: LEX_AUTONOMOUS_MODE is for well-specified briefs — the lawyer has
                    # already included everything; extra prompts add friction, not value.
                    _core = ("matter_type", "parties", "jurisdiction", "purpose")
                    if cfg.autonomous_mode and all(state.get(f) for f in _core):
                        console.print(Panel(
                            "[dim]Autonomous mode — proceeding without clarifying questions.[/dim]\n"
                            + "\n".join(f"  [dim]{i+1}. {q}[/dim]" for i, q in enumerate(questions)),
                            title="[bold yellow]Auto-proceeding (LEX_AUTONOMOUS_MODE=true)[/bold yellow]",
                            border_style="yellow",
                        ))
                        state = {**state, "intake_complete": True, "clarifying_questions": [], "pending_questions": []}
                        continue

                    console.print()
                    console.print(Panel(
                        "\n".join(f"[bold cyan]{i+1}.[/bold cyan] {q}" for i, q in enumerate(questions)),
                        title="[bold yellow]Themis needs a few more details[/bold yellow]",
                        border_style="yellow",
                    ))
                    console.print()

                    answers = Prompt.ask(
                        "[bold]Your answers[/bold] (answer all questions above, separated by commas or in full sentences)",
                        console=console,
                    )
                    _compress_paste_display(console, answers)

                    state = {
                        **state,
                        "user_input": f"{state['user_input']}\n\nAnswers to your questions: {answers}",
                        "messages": list(state.get("messages", [])) + [{"role": "user", "content": answers}],
                    }
                    continue

            if state.get("draft_output"):
                _render_draft(state)

                if cfg.auto_save_matter:
                    _save_session_and_memory(state, cfg)

                # WHY: wisdom extraction is fire-and-forget — runs in background so
                # it never adds latency to draft delivery. Errors are suppressed inside.
                from themis.memory.wisdom import extract_and_save_wisdom
                asyncio.ensure_future(extract_and_save_wisdom(state, cfg))

                break

            console.print("[yellow]No draft was produced. Try again with more detail.[/yellow]")
            break

    finally:
        unregister_draft_stream(matter_id)


def _blank_state(
    brief: str,
    matter_id: str,
    output_path: Optional[str] = None,
    agent_config: Optional[dict] = None,
    forced_skill_names: Optional[List[str]] = None,
    redline_source_path: Optional[str] = None,
    chamber_enabled: bool = False,
) -> SeniorCounselState:
    return {  # type: ignore[return-value]
        "user_input": brief,
        "matter_id": matter_id,
        "intake_complete": False,
        "citations_verified": False,
        "messages": [{"role": "user", "content": brief}],
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
        "active_agent": agent_config,
        "error": None,
        "next_node": None,
        "grounded_citations": None,
        "retrieval_chunks": None,
        "docx_path": output_path,
        "forced_skill_names": forced_skill_names,
        "redline_source_path": redline_source_path,
        "chamber_enabled": chamber_enabled or None,
    }


def _save_session_and_memory(state: SeniorCounselState, cfg: LexConfig) -> None:
    from themis.memory.matter_memory import save_matter_memory
    from themis.memory.session_store import init_db, save_session

    try:
        init_db(cfg.sessions_db)
        session_id = save_session(state, cfg.sessions_db)
        mem_path = save_matter_memory(
            state.get("matter_id") or "unknown",
            state,
            cfg.matters_dir,
            firm_id=cfg.default_firm_id,
        )
        console.print(
            f"\n[dim]✓ Session saved (ID: {session_id}) | "
            f"Matter memory: {mem_path}[/dim]"
        )
    except Exception as e:
        console.print(f"\n[dim yellow]Note: Could not save session — {e}[/dim yellow]")


def _render_draft(state: SeniorCounselState) -> None:
    agent = state.get("active_agent")
    agent_label = ""
    if agent:
        agent_label = f" via [cyan]@{agent['id']}[/cyan]"

    console.print()
    console.print(
        Panel(
            Markdown(state["draft_output"]),
            title=f"[bold green]⚖ Draft Complete{agent_label}[/bold green]",
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
    if agent:
        footer_parts.append(f"Agent: @{agent['id']}")

    console.print()
    console.print(f"[dim]{' | '.join(footer_parts)}[/dim]")


# ---------------------------------------------------------------------------
# lex setup
# ---------------------------------------------------------------------------

@app.command()
def setup() -> None:
    """
    First-run setup wizard — creates your lawyer profile (SOUL.md).
    Run this once before your first draft for personalised output.
    """
    from themis.memory.soul import run_setup_wizard, soul_path
    from themis.memory.session_store import init_db

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

    try:
        init_db(cfg.sessions_db)
        console.print(f"[dim]Sessions database ready at {cfg.sessions_db}[/dim]")
    except Exception as e:
        console.print(f"[dim yellow]Could not initialise sessions DB: {e}[/dim yellow]")


# ---------------------------------------------------------------------------
# lex config — interactive provider/model wizard + show/test subcommands
# ---------------------------------------------------------------------------

config_app = typer.Typer(name="config", help="Configure Themis — provider, model, keys.")
app.add_typer(config_app, name="config")


def _load_config_yaml(path: str) -> dict:
    """Load persisted config from YAML, returning empty dict if missing."""
    import yaml
    p = Path(path).expanduser()
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config_yaml(path: str, data: dict) -> None:
    import yaml
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


@config_app.callback(invoke_without_command=True)
def config(ctx: typer.Context) -> None:
    """
    Interactive wizard to configure your LLM provider and model.

    Run with no subcommand to start the wizard.
    Use `lex config show` to print current settings.
    Use `lex config test` to verify your API key works.
    """
    if ctx.invoked_subcommand is not None:
        return

    from themis.providers import list_providers

    cfg = LexConfig()
    saved = _load_config_yaml(cfg.config_yaml)

    console.print()
    console.print(Rule(title="[bold cyan] Themis Provider Setup [/bold cyan]", style="cyan"))
    console.print()

    profiles = list_providers()
    current_provider = saved.get("model_provider", cfg.model_provider)

    # Build display list
    rows = []
    for i, p in enumerate(profiles):
        marker = "●" if p.name == current_provider else "○"
        tags = []
        if p.free:
            tags.append("[green]free[/green]")
        if p.eu_sovereign:
            tags.append("[blue]EU[/blue]")
        if p.local:
            tags.append("[magenta]local[/magenta]")
        tag_str = " ".join(tags)
        key_str = f"({', '.join(p.env_vars)})" if p.env_vars else "(no key needed)"
        rows.append(
            f"  [cyan]{i + 1}[/cyan]. {marker} [bold]{p.display_name}[/bold] "
            f"[dim]{key_str}[/dim] {tag_str}"
        )
        console.print(rows[-1])
        console.print(f"     [dim]{p.description}[/dim]")
        console.print()

    choice_str = Prompt.ask(
        "Select provider [cyan](number)[/cyan]",
        default=str(next((i + 1 for i, p in enumerate(profiles) if p.name == current_provider), 1)),
        console=console,
    )
    try:
        choice_idx = int(choice_str) - 1
        chosen = profiles[choice_idx]
    except (ValueError, IndexError):
        console.print("[red]Invalid choice.[/red]")
        raise typer.Exit(1)

    # Model selection
    console.print()
    current_model = saved.get("default_model", cfg.default_model)
    if chosen.default_model and chosen.default_model != current_model:
        suggested = chosen.default_model
    else:
        suggested = current_model

    model_name = Prompt.ask(
        f"Model name [dim](e.g. {chosen.default_model or 'model-name'})[/dim]",
        default=suggested,
        console=console,
    )

    # API key collection for providers that need one
    for env_var in chosen.env_vars:
        import os
        if not os.environ.get(env_var):
            console.print()
            key_val = Prompt.ask(
                f"[bold]{env_var}[/bold] [dim](leave blank to skip)[/dim]",
                password=True,
                default="",
                console=console,
            )
            if key_val:
                # Write to .env in cwd if it exists, otherwise advise
                env_path = Path(".env")
                if env_path.exists():
                    with open(env_path, "a") as f:
                        f.write(f"\n{env_var}={key_val}\n")
                    console.print(f"[dim]✓ Appended {env_var} to .env[/dim]")
                else:
                    console.print(
                        f"[yellow]Set [bold]{env_var}={key_val}[/bold] in your shell "
                        f"or create a .env file.[/yellow]"
                    )
                    os.environ[env_var] = key_val

    # Custom base URL for local providers
    base_url = chosen.base_url
    if chosen.local or chosen.name == "custom":
        base_url = Prompt.ask(
            "Base URL",
            default=chosen.base_url or "http://localhost:11434",
            console=console,
        )

    # Save to YAML
    saved.update({
        "model_provider": chosen.name,
        "default_model": model_name,
    })
    if base_url:
        saved["model_base_url"] = base_url
    _save_config_yaml(cfg.config_yaml, saved)

    console.print()
    console.print(
        Panel(
            f"[bold]Provider:[/bold] {chosen.display_name}\n"
            f"[bold]Model:[/bold] {model_name}\n"
            f"[bold]Config file:[/bold] {cfg.config_yaml}",
            title="[bold green]✓ Config saved[/bold green]",
            border_style="green",
        )
    )
    console.print()
    console.print("[dim]Run [bold]lex config test[/bold] to verify your connection.[/dim]")


@config_app.command("show")
def config_show() -> None:
    """Print current Themis configuration."""
    from themis.providers import build_model_string, get_provider_profile

    cfg = LexConfig()
    saved = _load_config_yaml(cfg.config_yaml)
    model_str = build_model_string(cfg)
    profile = get_provider_profile(cfg.model_provider)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()
    table.add_row("Provider", f"[bold]{profile.display_name if profile else cfg.model_provider}[/bold]")
    table.add_row("Model", f"[bold cyan]{model_str}[/bold cyan]")
    table.add_row("Chat model (intake)", cfg.chat_model or "[dim]same as draft model[/dim]")
    if cfg.model_base_url:
        table.add_row("Base URL", cfg.model_base_url)
    table.add_row("Config YAML", str(Path(cfg.config_yaml).expanduser()))
    table.add_row("Home dir", str(Path(cfg.home_dir).expanduser()))
    table.add_row("Kanoon backend", cfg.kanoon_backend)
    table.add_row("Auto-verify citations", str(cfg.auto_verify_citations))
    if saved:
        table.add_row("YAML overrides", ", ".join(saved.keys()))

    console.print()
    console.print(Panel(table, title="[bold cyan]Themis Config[/bold cyan]", border_style="cyan"))


@config_app.command("test")
def config_test() -> None:
    """Fire a test LLM call to verify your API key and model work."""
    import litellm
    from themis.providers import build_model_string

    cfg = LexConfig()
    model_str = build_model_string(cfg)

    console.print()
    console.print(f"[dim]Testing [bold]{model_str}[/bold]...[/dim]")

    kwargs: dict = {
        "model": model_str,
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
        "max_tokens": 10,
    }
    if cfg.model_base_url:
        kwargs["api_base"] = cfg.model_base_url

    try:
        resp = asyncio.run(litellm.acompletion(**kwargs))
        reply = resp.choices[0].message.content or ""
        console.print(
            Panel(
                f"[bold green]✓ Connected[/bold green] to [bold]{model_str}[/bold]\n"
                f"[dim]Response: {reply.strip()[:80]}[/dim]",
                border_style="green",
            )
        )
    except Exception as e:
        console.print(
            Panel(
                f"[bold red]✗ Connection failed[/bold red]\n[red]{e}[/red]",
                border_style="red",
            )
        )


@config_app.command("tools")
def config_tools() -> None:
    """Configure research tools and API keys (Indian Kanoon, eCourts, Tavily, etc.)."""
    from themis.memory.soul import _setup_research_tools
    cfg = LexConfig()
    _setup_research_tools(cfg.home_dir)


# ---------------------------------------------------------------------------
# lex agent — create, list, delete, show
# ---------------------------------------------------------------------------

@agent_app.command("list")
def agent_list() -> None:
    """List all available agent personas (bundled + custom)."""
    from themis.agents.registry import list_agents
    from themis.agents.faces import FACES

    cfg = LexConfig()
    agents = list_agents(cfg.agents_dir)

    if not agents:
        console.print("[yellow]No agents found.[/yellow]")
        raise typer.Exit(0)

    console.print()
    console.print(Rule(title="[bold cyan] Available Agents [/bold cyan]", style="cyan"))
    console.print()

    for ag in agents:
        face_key = ag.get("face", "sharp_counsel")
        face = FACES.get(face_key, FACES["sharp_counsel"])
        source_badge = "[dim]bundled[/dim]" if ag.get("source") == "bundled" else "[green]custom[/green]"

        console.print(
            Panel(
                f"[bold cyan]{face['art']}[/bold cyan]\n"
                f"[bold]@{ag['id']}[/bold]  ·  {ag.get('name', '')}  ·  {source_badge}\n"
                f"[dim]{ag.get('tagline', '')}[/dim]\n\n"
                f"[dim]Tone:[/dim] {ag.get('tone', '—')}  ·  "
                f"[dim]Skills:[/dim] {', '.join(ag.get('skills', [])) or '—'}",
                border_style="cyan",
                padding=(0, 2),
            )
        )

    console.print()
    console.print("[dim]Use in a draft: [bold]lex draft \"@agentname your brief\"[/bold] "
                  "or [bold]lex draft --agent agentname \"your brief\"[/bold][/dim]")


@agent_app.command("show")
def agent_show(
    agent_id: str = typer.Argument(..., help="Agent ID to show (e.g. vikram)")
) -> None:
    """Show full details and persona of a specific agent."""
    from themis.agents.registry import load_agent
    from themis.agents.faces import FACES

    cfg = LexConfig()
    agent = load_agent(agent_id.lstrip("@"), cfg.agents_dir)

    if not agent:
        console.print(f"[red]Agent @{agent_id} not found. Run [bold]lex agent list[/bold] to see available agents.[/red]")
        raise typer.Exit(1)

    face_key = agent.get("face", "sharp_counsel")
    face = FACES.get(face_key, FACES["sharp_counsel"])

    console.print()
    console.print(
        Panel(
            f"[bold cyan]{face['art']}[/bold cyan]\n\n"
            f"[bold]Handle:[/bold]   @{agent['id']}\n"
            f"[bold]Name:[/bold]     {agent.get('name', '—')}\n"
            f"[bold]Full name:[/bold] {agent.get('full_name', '—')}\n"
            f"[bold]Tagline:[/bold]  {agent.get('tagline', '—')}\n"
            f"[bold]Tone:[/bold]     {agent.get('tone', '—')}\n"
            f"[bold]Skills:[/bold]   {', '.join(agent.get('skills', [])) or '—'}\n\n"
            f"[bold]Persona:[/bold]\n[italic dim]{agent.get('persona', '—')}[/italic dim]",
            title=f"[bold cyan]Agent — @{agent['id']}[/bold cyan]",
            border_style="cyan",
            padding=(1, 3),
        )
    )


@agent_app.command("create")
def agent_create() -> None:
    """
    Interactively create a custom agent persona.
    Saved to ~/.themis/agents/ and immediately usable with @handle.
    """
    from themis.agents.registry import create_agent, load_agent
    from themis.agents.faces import FACES, list_faces_table

    cfg = LexConfig()

    console.print()
    console.print(Rule(title="[bold cyan] Create Custom Agent [/bold cyan]", style="cyan"))
    console.print()
    console.print(
        Panel(
            "Create a custom advocate persona that Themis will embody.\n"
            "Give them a name, a personality, and choose their skills.\n\n"
            "[dim]Use [bold]@handle[/bold] in any brief to invoke this agent.[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()

    def ask(prompt_text: str, hint: str = "", default: str = "") -> str:
        if hint:
            console.print(f"  [dim]{hint}[/dim]")
        val = Prompt.ask(f"  [bold cyan]›[/bold cyan] {prompt_text}", default=default, console=console)
        return val.strip()

    # Handle / ID
    handle = ask("Agent handle", "@handle — used in briefs (e.g. kavya, raj, felix)")
    handle = handle.lstrip("@").lower().replace(" ", "_")
    if not handle:
        console.print("[red]Handle is required. Exiting.[/red]")
        raise typer.Exit(1)

    existing = load_agent(handle, cfg.agents_dir)
    if existing and existing.get("source") == "custom":
        overwrite = Prompt.ask(
            f"  [yellow]Agent @{handle} already exists. Overwrite?[/yellow]",
            choices=["y", "n"], default="n", console=console,
        )
        if overwrite.lower() != "y":
            raise typer.Exit(0)

    console.print()
    name = ask("Display name", "How this agent's name appears in the UI (e.g. Kavya)")
    full_name = ask("Full formal name", "Used in document headers (e.g. Advocate Kavya Singh)", default=name)
    tagline = ask("One-line tagline", "What this agent is known for (e.g. 'Arguing until the bench agrees.')")
    tone = ask("Drafting tone", "E.g. Aggressive formal, Accessible English, Conciliatory", default="Senior formal")

    # Persona description
    console.print()
    console.print("  [dim]Write this agent's personality and approach. Think: 'You are [name]...'[/dim]")
    console.print("  [dim]This is injected into every system prompt when this agent is active.[/dim]")
    console.print()
    persona_lines = []
    console.print("  [bold cyan]›[/bold cyan] [bold]Persona[/bold] [dim](type multiple lines, empty line to finish):[/dim]")
    while True:
        line = console.input("    ")
        if not line.strip():
            break
        persona_lines.append(line)
    persona = "\n".join(persona_lines)

    # Face selection
    console.print()
    faces = list_faces_table()
    face_table = Table(show_header=True, box=None, padding=(0, 2))
    face_table.add_column("#", style="bold cyan", width=3)
    face_table.add_column("Key", style="bold")
    face_table.add_column("Name")
    face_table.add_column("Description", style="dim")
    for i, f in enumerate(faces, 1):
        face_table.add_row(str(i), f["key"], f["name"], f["description"])
    console.print("  [dim]Choose a face (ASCII avatar):[/dim]")
    console.print(face_table)
    console.print()
    face_raw = ask("Face (number or key)", default="1")
    try:
        face_key = faces[int(face_raw) - 1]["key"]
    except (ValueError, IndexError):
        face_key = face_raw if face_raw in FACES else "sharp_counsel"

    # Skills
    console.print()
    import os
    bundled_skills_dir = os.path.join(os.path.dirname(__file__), "skills")
    available_skills = [
        f.stem for f in sorted(
            list(__import__("pathlib").Path(bundled_skills_dir).glob("*.md"))
        )
    ]
    skill_table = Table(show_header=False, box=None, padding=(0, 2))
    skill_table.add_column("#", style="bold cyan", width=3)
    skill_table.add_column("Skill")
    for i, s in enumerate(available_skills, 1):
        skill_table.add_row(str(i), s)
    console.print("  [dim]Available skills (comma-separated numbers or names):[/dim]")
    console.print(skill_table)
    console.print()
    skills_raw = ask("Skills to enable", "E.g. 1,3 or civil_litigation,filing_checklist", default="")
    chosen_skills: list[str] = []
    if skills_raw:
        for part in skills_raw.split(","):
            part = part.strip()
            try:
                idx = int(part) - 1
                if 0 <= idx < len(available_skills):
                    chosen_skills.append(available_skills[idx])
            except ValueError:
                if part:
                    chosen_skills.append(part)

    agent_data = {
        "id": handle,
        "name": name,
        "full_name": full_name,
        "tagline": tagline,
        "tone": tone,
        "persona": persona,
        "face": face_key,
        "skills": chosen_skills,
    }

    # Show preview
    console.print()
    console.print(Rule(title="[dim] Preview [/dim]", style="dim"))
    console.print()
    face_art = FACES.get(face_key, FACES["sharp_counsel"])["art"]
    console.print(
        Panel(
            f"[bold cyan]{face_art}[/bold cyan]\n\n"
            f"[bold]@{handle}[/bold]  ·  {name}\n"
            f"[dim]{tagline}[/dim]\n\n"
            f"[dim]Tone:[/dim] {tone}  ·  [dim]Skills:[/dim] {', '.join(chosen_skills) or '—'}\n\n"
            f"[dim]{persona[:200]}{'...' if len(persona) > 200 else ''}[/dim]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()

    confirm = Prompt.ask("  Save this agent?", choices=["y", "n"], default="y", console=console)
    if confirm.lower() != "y":
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    path = create_agent(agent_data, cfg.agents_dir)

    console.print()
    console.print(
        Panel(
            f"[green]✓ Agent [bold]@{handle}[/bold] created.[/green]\n\n"
            f"Saved to: [dim]{path}[/dim]\n\n"
            f"Use in a brief:  [bold cyan]lex draft \"@{handle} your matter here\"[/bold cyan]\n"
            f"Or with flag:    [bold cyan]lex draft --agent {handle} \"your matter here\"[/bold cyan]",
            title="[bold green]✓ Agent Created[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )


@agent_app.command("delete")
def agent_delete(
    agent_id: str = typer.Argument(..., help="Agent ID to delete (e.g. vikram)")
) -> None:
    """Delete a custom agent persona."""
    from themis.agents.registry import delete_agent

    cfg = LexConfig()
    agent_id = agent_id.lstrip("@").lower()

    confirm = Prompt.ask(
        f"  [yellow]Delete agent @{agent_id}? This cannot be undone.[/yellow]",
        choices=["y", "n"],
        default="n",
        console=console,
    )
    if confirm.lower() != "y":
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    deleted = delete_agent(agent_id, cfg.agents_dir)
    if deleted:
        console.print(f"[green]✓ Agent @{agent_id} deleted.[/green]")
    else:
        console.print(
            f"[red]Could not delete @{agent_id}. "
            "Only custom agents can be deleted (bundled agents are read-only).[/red]"
        )
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# lex matter list / lex matter show
# ---------------------------------------------------------------------------

@matter_app.command("list")
def matter_list() -> None:
    """List all saved matters, most recent first."""
    from themis.memory.matter_memory import list_matters

    cfg = LexConfig()
    matters = list_matters(cfg.matters_dir, firm_id=cfg.default_firm_id)

    if not matters:
        console.print("[yellow]No matters saved yet. Run [bold]lex draft[/bold] to create your first.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Saved Matters", border_style="cyan", show_lines=True)
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
    from themis.memory.matter_memory import load_matter_memory

    cfg = LexConfig()
    memory = load_matter_memory(matter_id, cfg.matters_dir, firm_id=cfg.default_firm_id)

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


# ---------------------------------------------------------------------------
# lex search
# ---------------------------------------------------------------------------

@app.command()
def search(query: str = typer.Argument(..., help="Full-text search query across all past matters")) -> None:
    """Search all past matters by keyword."""
    from themis.memory.session_store import search_sessions

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


# ---------------------------------------------------------------------------
# lex reminder add / list / delete
# ---------------------------------------------------------------------------

reminder_app = typer.Typer(name="reminder", help="Manage hearing reminders.")
app.add_typer(reminder_app, name="reminder")


@reminder_app.command("add")
def reminder_add(
    matter_id: str = typer.Option(..., "--matter-id", "-m", help="Matter ID (e.g. M-ABCD1234)"),
    date: str = typer.Option(..., "--date", "-d", help="Hearing date in YYYY-MM-DD format"),
    note: str = typer.Option("", "--note", "-n", help="Short note (e.g. 'HC hearing — injunction')"),
    days_before: int = typer.Option(1, "--days-before", help="Fire reminder N days before the hearing"),
) -> None:
    """Set a hearing reminder for a matter."""
    from themis.memory.session_store import add_reminder

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
    from themis.memory.session_store import list_reminders

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
    reminder_id: int = typer.Argument(..., help="Reminder ID to delete"),
) -> None:
    """Delete a reminder by ID."""
    from themis.memory.session_store import delete_reminder

    cfg = LexConfig()
    deleted = delete_reminder(reminder_id, sessions_db=cfg.sessions_db)
    if deleted:
        console.print(f"[green]✓ Reminder {reminder_id} deleted.[/green]")
    else:
        console.print(f"[red]No reminder found with ID {reminder_id}.[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# lex gateway / voice
# ---------------------------------------------------------------------------

@app.command()
def gateway(
    service: str = typer.Argument("telegram", help="Gateway service to start: telegram, web"),
) -> None:
    """Start a messaging gateway for Themis."""
    cfg = LexConfig()

    if service.lower() == "telegram":
        from themis.gateway.telegram import run_telegram_bot
        run_telegram_bot(cfg)
    elif service.lower() in ("web", "api", "control-plane", "server"):
        import uvicorn
        from themis.gateway.control_plane import app as fastapi_app
        console.print(f"[bold cyan]⚖ Themis Control Plane[/bold cyan] — http://{cfg.control_plane_host}:{cfg.control_plane_port}")
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
    """Start the Themis Voice AI gateway server."""
    import uvicorn
    from themis.gateway.control_plane import app as fastapi_app

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
            title="[bold cyan]⚖ Themis Voice Gateway[/bold cyan]",
            border_style="cyan",
        )
    )

    if twilio:
        twilio_sid = getattr(cfg, 'twilio_account_sid', None)
        twilio_num = getattr(cfg, 'twilio_phone_number', None)
        console.print(
            Panel(
                f"[bold]Twilio Account SID:[/bold] {twilio_sid or '[red]NOT SET[/red]'}\n"
                f"[bold]Twilio Phone Number:[/bold] {twilio_num or '[red]NOT SET[/red]'}\n\n"
                f"[bold]Incoming call webhook:[/bold] https://YOUR-DOMAIN/voice/incoming\n"
                f"[bold]Gather webhook:[/bold] https://YOUR-DOMAIN/voice/gather\n\n"
                f"[dim]Use ngrok to expose locally: ngrok http {port}[/dim]\n"
                "[dim]Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER in .env[/dim]",
                title="[bold yellow]📞 Twilio Phone Gateway Setup[/bold yellow]",
                border_style="yellow",
            )
        )

    console.print(f"\n[dim]Starting server on {host}:{port}... (Ctrl+C to stop)[/dim]\n")
    uvicorn.run(fastapi_app, host=host, port=port, reload=reload, log_level="info")


# ---------------------------------------------------------------------------
# lex research — research-only mode (no draft)
# ---------------------------------------------------------------------------

@app.command()
def research(
    brief: Optional[str] = typer.Argument(
        None,
        help="Matter brief to research. Returns case law table — no draft produced.",
    ),
    matter_id: Optional[str] = typer.Option(None, "--matter-id", "-m", help="Attach to an existing matter ID"),
    save: bool = typer.Option(False, "--save", "-s", help="Save research findings to matter memory"),
) -> None:
    """
    Research Indian case law for a matter — no draft produced.

    Returns a table of verified case citations with relevance notes.
    Use lex draft once you're ready to produce the document.

      lex research "property dispute injunction Delhi"
      lex research "bail application NDPS Section 37" --save
    """
    cfg = LexConfig()
    from themis.nodes._llm import setup_litellm_cache
    setup_litellm_cache(cfg)

    if not brief:
        brief = Prompt.ask(
            "[bold cyan]What do you want to research?[/bold cyan] [dim](matter type, key issue, jurisdiction)[/dim]",
            console=console,
        )
    if not brief.strip():
        console.print("[red]No research query provided.[/red]")
        raise typer.Exit(1)

    session_matter_id = matter_id or f"R-{uuid.uuid4().hex[:8].upper()}"

    console.print()
    console.print(Panel(
        f"[bold]Query:[/bold] {brief}\n[bold]Matter ID:[/bold] {session_matter_id}",
        title="[bold cyan]⚖ Themis Research[/bold cyan]",
        border_style="cyan",
    ))
    console.print()

    asyncio.run(_run_research(brief, session_matter_id, cfg, save))


async def _run_research(brief: str, matter_id: str, cfg: LexConfig, save: bool) -> None:
    graph = get_graph()
    state = _blank_state(brief, matter_id)
    state["research_only"] = True  # type: ignore[typeddict-unknown-key]

    _GRAPH_TIMEOUT = 120
    final_state = state

    with console.status("[bold cyan]🔍  researching Indian case law...[/bold cyan]", spinner="dots") as status:
        anim = LexAnimator(status, phase="research")
        anim.start()
        try:
            async with asyncio.timeout(_GRAPH_TIMEOUT):
                async for chunk in graph.astream(
                    state,
                    config={"configurable": {"thread_id": matter_id}},
                ):
                    for node_name, node_output in chunk.items():
                        if isinstance(node_output, dict):
                            final_state = {**final_state, **node_output}
                            if node_name == "intake" and node_output.get("intake_complete"):
                                status.update("[bold cyan]Searching Indian Kanoon and case databases...[/bold cyan]")
                            elif node_name == "research":
                                anim.stop()
        except asyncio.TimeoutError:
            anim.stop()
            console.print(f"\n[bold red]⏱ Timed out after {_GRAPH_TIMEOUT}s.[/bold red]")
            return
        except Exception as exc:
            anim.stop()
            console.print(f"\n[bold red]Research error:[/bold red] {exc}")
            return
        finally:
            anim.stop()

    if final_state.get("error"):
        console.print(f"\n[bold red]Error:[/bold red] {final_state['error']}")
        return

    _render_research(final_state)

    if save:
        _save_session_and_memory(final_state, cfg)


def _render_research(state: dict) -> None:
    findings = state.get("research_findings") or []
    statutes = state.get("statutes_cited") or []
    limitation = state.get("limitation_analysis")

    console.print()

    if not findings:
        console.print(Panel(
            "[yellow]No case law found for this query.[/yellow]\n"
            "Try a more specific brief or check your Indian Kanoon API key.",
            title="[bold yellow]Research Results[/bold yellow]",
            border_style="yellow",
        ))
        return

    table = Table(
        title=f"Research Findings — {state.get('matter_id', '')}",
        border_style="cyan",
        show_lines=True,
        expand=True,
    )
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Case Name", style="bold", min_width=20)
    table.add_column("Citation", style="yellow", min_width=18)
    table.add_column("Relevance", min_width=30)
    table.add_column("Source", style="dim", width=10)

    citable = [f for f in findings if f.get("citation")]
    for i, f in enumerate(citable, 1):
        table.add_row(
            str(i),
            f.get("case_name") or "—",
            f.get("citation") or "—",
            (f.get("relevance") or f.get("snippet") or "—")[:120],
            f.get("source") or "—",
        )

    console.print(table)

    if statutes:
        console.print()
        console.print(Panel(
            "\n".join(f"• {s}" for s in statutes),
            title="[bold blue]Statutes Identified[/bold blue]",
            border_style="blue",
        ))

    if limitation:
        console.print()
        console.print(Panel(
            limitation,
            title="[bold yellow]Limitation Analysis[/bold yellow]",
            border_style="yellow",
        ))

    console.print()
    console.print(
        f"[dim]{len(citable)} case(s) found  ·  Matter ID: {state.get('matter_id')}[/dim]\n"
        "[dim]Ready to draft? Run: [bold]lex draft \"your brief\"[/bold][/dim]"
    )


# ---------------------------------------------------------------------------
# lex query — search your KB across all past matter research
# ---------------------------------------------------------------------------

@app.command()
def query(
    question: Optional[str] = typer.Argument(None, help="What to search for across past matters"),
    limit: int = typer.Option(15, "--limit", "-n", help="Maximum results to show"),
) -> None:
    """
    Query your knowledge base — search case law from all past matters.

    Searches research findings stored from previous lex draft and lex research runs.
    Qdrant vector search is used automatically if QDRANT_ENABLED=true.

      lex query "Section 138 NI Act cheque dishonour"
      lex query "injunction property dispute Delhi" --limit 20
    """
    cfg = LexConfig()

    if not question:
        question = Prompt.ask(
            "[bold cyan]Search your knowledge base[/bold cyan]",
            console=console,
        )
    if not question.strip():
        console.print("[red]No query provided.[/red]")
        raise typer.Exit(1)

    console.print()

    from themis.tools.kb_query import search_kb, search_kb_qdrant

    with console.status("[bold cyan]🔍  searching knowledge base...[/bold cyan]", spinner="dots"):
        results = search_kb(question, sessions_db=cfg.sessions_db, limit=limit)

        if cfg.qdrant_enabled:
            qdrant_results = search_kb_qdrant(
                question,
                qdrant_url=cfg.qdrant_url,
                api_key=cfg.qdrant_api_key,
                limit=10,
            )
            seen = {r["citation"] for r in results}
            for r in qdrant_results:
                if r["citation"] not in seen:
                    results.append(r)
                    seen.add(r["citation"])
            results = results[:limit]

    if not results:
        console.print(Panel(
            f"[yellow]No results found for: [bold]{question}[/bold][/yellow]\n\n"
            "Your KB is built from research in past matters.\n"
            "Run [bold]lex research[/bold] or [bold]lex draft[/bold] to add cases to your KB.",
            title="[bold yellow]Knowledge Base Query[/bold yellow]",
            border_style="yellow",
        ))
        return

    table = Table(
        title=f"KB Results: \"{question}\"",
        border_style="cyan",
        show_lines=True,
        expand=True,
    )
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Case Name", style="bold", min_width=22)
    table.add_column("Citation", style="yellow", min_width=16)
    table.add_column("Relevance", min_width=30)
    table.add_column("Matter", style="dim", width=14)
    table.add_column("Src", style="dim", width=8)

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r["case_name"],
            r["citation"],
            r["relevance"][:100],
            r["matter_id"],
            r["source"][:8],
        )

    console.print(table)
    console.print(f"\n[dim]{len(results)} result(s) — use [bold]lex matter show <MATTER-ID>[/bold] for full context[/dim]")


# ---------------------------------------------------------------------------
# lex qa — document QA with inline citations ([1], [2])
# ---------------------------------------------------------------------------

@app.command()
def qa(
    file: str = typer.Argument(..., help="Path to a PDF or DOCX file"),
) -> None:
    """
    Ask questions about a PDF or DOCX — answers include inline [N] citations.

    Each answer shows the relevant passage, page, and clause so you can
    verify every claim without reading the whole document.

      lex qa agreement.pdf
      lex qa judgment.docx
    """
    file_path = Path(file).expanduser().resolve()
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    cfg = LexConfig()
    from themis.nodes.document_qa import run_document_qa_session
    asyncio.run(run_document_qa_session(file_path, cfg))


# ---------------------------------------------------------------------------
# lex contract — contract workspace (review, draft, playbook, lifecycle)
# ---------------------------------------------------------------------------

contract_app = typer.Typer(name="contract", help="Contract workspace — review, draft, playbooks, lifecycle.")
app.add_typer(contract_app, name="contract")


@contract_app.command("review")
def contract_review_cmd(
    file: str = typer.Argument(..., help="Path to contract PDF or text file"),
    playbook: Optional[str] = typer.Option(None, "--playbook", "-p", help="Playbook ID to apply (lex contract playbook list)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save risk report to file"),
) -> None:
    """
    Review a contract PDF — risk analysis, clause flags, deviations from firm playbook.

      lex contract review agreement.pdf
      lex contract review agreement.pdf --playbook nda --output review.md
    """
    cfg = LexConfig()
    from themis.nodes._llm import setup_litellm_cache
    setup_litellm_cache(cfg)

    file_path = Path(file).expanduser()
    if not file_path.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    playbook_prompt = ""
    if playbook:
        from themis.contract.playbook import load_playbook, playbook_to_prompt
        pb = load_playbook(playbook, cfg.playbooks_dir)
        if pb:
            playbook_prompt = playbook_to_prompt(pb)
            console.print(f"[dim]Playbook loaded: {pb['name']}[/dim]")
        else:
            console.print(f"[yellow]Playbook '{playbook}' not found. Continuing without playbook.[/yellow]")

    matter_id = f"CR-{uuid.uuid4().hex[:8].upper()}"

    console.print()
    console.print(Panel(
        f"[bold]File:[/bold] {file_path.name}\n"
        f"[bold]Matter ID:[/bold] {matter_id}\n"
        f"[bold]Playbook:[/bold] {playbook or '—'}",
        title="[bold cyan]⚖ Contract Review[/bold cyan]",
        border_style="cyan",
    ))
    console.print()

    asyncio.run(_run_contract_review(str(file_path), matter_id, cfg, playbook_prompt, output))


async def _run_contract_review(
    file_path: str,
    matter_id: str,
    cfg: LexConfig,
    playbook_prompt: str,
    output_path: Optional[str],
) -> None:
    graph = get_graph()
    state = _blank_state(f"Review contract: {file_path}", matter_id)
    state["workflow_mode"] = "contract_review"  # type: ignore[typeddict-unknown-key]
    state["contract_upload_path"] = file_path  # type: ignore[typeddict-unknown-key]
    if playbook_prompt:
        # Inject playbook into active_skill slot so draft/contract nodes pick it up
        state["active_skill"] = playbook_prompt  # type: ignore[typeddict-unknown-key]

    _GRAPH_TIMEOUT = 180
    final_state: dict = state  # type: ignore[assignment]

    with console.status("[bold cyan]📋  reviewing contract...[/bold cyan]", spinner="dots") as status:
        anim = LexAnimator(status, phase="review")
        anim.start()
        try:
            async with asyncio.timeout(_GRAPH_TIMEOUT):
                async for chunk in graph.astream(
                    state,
                    config={"configurable": {"thread_id": matter_id}},
                ):
                    for node_name, node_output in chunk.items():
                        if isinstance(node_output, dict):
                            final_state = {**final_state, **node_output}
                            _print_node_done(status, anim, node_name, node_output)
        except asyncio.TimeoutError:
            anim.stop()
            console.print(f"\n[bold red]⏱ Timed out after {_GRAPH_TIMEOUT}s.[/bold red]")
            return
        except Exception as exc:
            anim.stop()
            console.print(f"\n[bold red]Review error:[/bold red] {exc}")
            return
        finally:
            anim.stop()

    if final_state.get("error"):
        console.print(f"\n[bold red]Error:[/bold red] {final_state['error']}")
        return

    report = final_state.get("contract_review_output") or final_state.get("draft_output") or ""
    if report:
        console.print()
        console.print(Panel(
            Markdown(report),
            title="[bold green]⚖ Contract Risk Report[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))
        if output_path:
            Path(output_path).write_text(report, encoding="utf-8")
            console.print(f"\n[dim]✓ Report saved to {output_path}[/dim]")


@contract_app.command("draft")
def contract_draft_cmd(
    brief: Optional[str] = typer.Argument(None, help="Describe the contract to draft"),
    playbook: Optional[str] = typer.Option(None, "--playbook", "-p", help="Playbook to apply"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to .docx"),
) -> None:
    """
    Draft a contract with firm playbook positions pre-loaded.

      lex contract draft "SaaS subscription agreement, 12 months, Delhi jurisdiction"
      lex contract draft --playbook nda "mutual NDA with TechCorp"
    """
    cfg = LexConfig()
    from themis.nodes._llm import setup_litellm_cache
    setup_litellm_cache(cfg)

    if not brief:
        brief = Prompt.ask(
            "[bold cyan]Describe the contract to draft[/bold cyan]",
            console=console,
        )
    if not brief.strip():
        console.print("[red]No brief provided.[/red]")
        raise typer.Exit(1)

    full_brief = brief
    playbook_prompt = ""
    if playbook:
        from themis.contract.playbook import load_playbook, playbook_to_prompt
        playbooks_dir = "~/.themis/playbooks"
        pb = load_playbook(playbook, playbooks_dir)
        if pb:
            playbook_prompt = playbook_to_prompt(pb)
            console.print(f"[dim]Playbook: {pb['name']}[/dim]")
            full_brief = f"{brief}\n\n[Apply firm playbook: {pb['name']}]"

    matter_id = f"CD-{uuid.uuid4().hex[:8].upper()}"

    console.print()
    console.print(Panel(
        f"[bold]Brief:[/bold] {brief}\n"
        f"[bold]Matter ID:[/bold] {matter_id}\n"
        f"[bold]Playbook:[/bold] {playbook or '—'}",
        title="[bold cyan]⚖ Contract Draft[/bold cyan]",
        border_style="cyan",
    ))
    console.print()

    async def _run() -> None:
        state = _blank_state(full_brief, matter_id, output)
        if playbook_prompt:
            state["active_skill"] = playbook_prompt  # type: ignore[typeddict-unknown-key]
        await _run_draft(full_brief, matter_id, cfg, None, output, None)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# lex contract playbook — manage firm negotiating positions
# ---------------------------------------------------------------------------

playbook_app = typer.Typer(name="playbook", help="Manage contract playbooks (firm positions).")
contract_app.add_typer(playbook_app, name="playbook")

_PLAYBOOKS_DIR = "~/.themis/playbooks"


@playbook_app.command("list")
def playbook_list() -> None:
    """List all contract playbooks (bundled + custom)."""
    from themis.contract.playbook import list_playbooks

    playbooks = list_playbooks(_PLAYBOOKS_DIR)
    if not playbooks:
        console.print("[yellow]No playbooks found.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Contract Playbooks", border_style="cyan", show_lines=True)
    table.add_column("ID", style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Positions", justify="right")
    table.add_column("Source", style="dim")

    for pb in playbooks:
        table.add_row(
            pb["id"],
            pb.get("name", "—"),
            pb.get("contract_type", "—"),
            str(len(pb.get("positions", []))),
            pb.get("source", "—"),
        )

    console.print()
    console.print(table)
    console.print("\n[dim]Use: [bold]lex contract playbook show <id>[/bold] · "
                  "[bold]lex contract review file.pdf --playbook <id>[/bold][/dim]")


@playbook_app.command("show")
def playbook_show(
    playbook_id: str = typer.Argument(..., help="Playbook ID to display")
) -> None:
    """Show all positions in a playbook."""
    from themis.contract.playbook import load_playbook

    pb = load_playbook(playbook_id, _PLAYBOOKS_DIR)
    if not pb:
        console.print(f"[red]Playbook '{playbook_id}' not found.[/red]")
        raise typer.Exit(1)

    lines = [
        f"[bold]ID:[/bold] {pb['id']}",
        f"[bold]Type:[/bold] {pb.get('contract_type', '—')}",
        f"[bold]Created:[/bold] {pb.get('created', '—')}",
        f"[bold]Notes:[/bold] {pb.get('notes', '—')}",
        "",
        "[bold]Positions:[/bold]",
    ]
    for pos in pb.get("positions", []):
        lines.append(f"\n  [bold cyan]• {pos.get('clause', '—')}[/bold cyan]")
        lines.append(f"    Position: {pos.get('our_position', '—')}")
        if pos.get("rationale"):
            lines.append(f"    [dim]Rationale: {pos['rationale']}[/dim]")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title=f"[bold cyan]Playbook — {pb.get('name', pb['id'])}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))


@playbook_app.command("add")
def playbook_add() -> None:
    """Interactively create a new contract playbook."""
    from themis.contract.playbook import create_playbook

    console.print()
    console.print(Rule(title="[bold cyan] Create Playbook [/bold cyan]", style="cyan"))
    console.print()

    def ask(prompt_text: str, hint: str = "", default: str = "") -> str:
        if hint:
            console.print(f"  [dim]{hint}[/dim]")
        return Prompt.ask(f"  [bold cyan]›[/bold cyan] {prompt_text}", default=default, console=console).strip()

    pb_id = ask("Playbook ID", "Short slug, e.g. nda_2024, saas_agreement")
    name = ask("Name", "Full display name")
    contract_type = ask("Contract type", "e.g. nda, shareholder_agreement, employment, saas")

    positions = []
    console.print("\n  [dim]Add clause positions (empty clause name to finish):[/dim]")
    while True:
        clause = ask("Clause name", "e.g. Non-compete, Governing law, Payment terms")
        if not clause:
            break
        our_position = ask("Our position", "What the firm always pushes for on this clause")
        rationale = ask("Rationale", "Why (one line)", default="")
        positions.append({"clause": clause, "our_position": our_position, "rationale": rationale})

    notes = ask("Notes", "Any general guidance for this playbook type", default="")

    data = {
        "id": pb_id or _slugify(name),
        "name": name,
        "contract_type": contract_type,
        "positions": positions,
        "notes": notes,
    }

    path = create_playbook(data, _PLAYBOOKS_DIR)
    console.print(Panel(
        f"[green]✓ Playbook [bold]{data['id']}[/bold] created.[/green]\n"
        f"Saved to: [dim]{path}[/dim]\n\n"
        f"Use: [bold cyan]lex contract review file.pdf --playbook {data['id']}[/bold cyan]",
        title="[bold green]✓ Playbook Created[/bold green]",
        border_style="green",
    ))


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9_]", "_", text.lower().strip())[:40]


@playbook_app.command("delete")
def playbook_delete(
    playbook_id: str = typer.Argument(..., help="Playbook ID to delete")
) -> None:
    """Delete a custom playbook."""
    from themis.contract.playbook import delete_playbook

    confirm = Prompt.ask(
        f"  [yellow]Delete playbook '{playbook_id}'?[/yellow]",
        choices=["y", "n"], default="n", console=console,
    )
    if confirm.lower() != "y":
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    if delete_playbook(playbook_id, _PLAYBOOKS_DIR):
        console.print(f"[green]✓ Playbook '{playbook_id}' deleted.[/green]")
    else:
        console.print(f"[red]Could not delete '{playbook_id}'. Only custom playbooks can be deleted.[/red]")
        raise typer.Exit(1)


@contract_app.command("lifecycle")
def contract_lifecycle_cmd(
    matter_id: str = typer.Argument(..., help="Matter ID to update lifecycle status"),
    status: Optional[str] = typer.Option(
        None, "--status", "-s",
        help="New status: draft | under_review | redlines_sent | executed | expired",
    ),
) -> None:
    """
    View or update the lifecycle status of a contract matter.

      lex contract lifecycle M-ABCD1234
      lex contract lifecycle M-ABCD1234 --status executed
    """
    from themis.memory.matter_memory import load_matter_memory
    from themis.memory.session_store import search_sessions

    cfg = LexConfig()

    _LIFECYCLE_STAGES = ["draft", "under_review", "redlines_sent", "executed", "expired"]
    _STAGE_COLORS = {
        "draft": "yellow",
        "under_review": "cyan",
        "redlines_sent": "blue",
        "executed": "green",
        "expired": "red",
    }

    if status:
        if status not in _LIFECYCLE_STAGES:
            console.print(f"[red]Invalid status '{status}'.[/red] Valid: {', '.join(_LIFECYCLE_STAGES)}")
            raise typer.Exit(1)

        # Store lifecycle update in matter memory as a note
        from themis.memory.matter_memory import save_matter_memory
        from datetime import datetime as dt
        pseudo_state: dict = {
            "matter_id": matter_id,
            "contract_lifecycle": status,
            "user_input": f"[lifecycle update] {status} — {dt.now().strftime('%Y-%m-%d %H:%M')}",
        }
        save_matter_memory(matter_id, pseudo_state, cfg.matters_dir, firm_id=cfg.default_firm_id)  # type: ignore[arg-type]
        color = _STAGE_COLORS.get(status, "cyan")
        console.print(f"\n[{color}]✓ Matter {matter_id} → [{status}][/{color}]\n")
        return

    # Show current lifecycle status from memory
    memory = load_matter_memory(matter_id, cfg.matters_dir, firm_id=cfg.default_firm_id)
    if not memory:
        console.print(f"[red]No matter found: {matter_id}[/red]")
        raise typer.Exit(1)

    # Extract lifecycle mentions from memory text
    current = "draft"
    for stage in reversed(_LIFECYCLE_STAGES):
        if stage in memory:
            current = stage
            break

    color = _STAGE_COLORS.get(current, "cyan")
    stages_display = " → ".join(
        f"[bold {color}]{s}[/bold {color}]" if s == current else f"[dim]{s}[/dim]"
        for s in _LIFECYCLE_STAGES
    )

    console.print()
    console.print(Panel(
        f"[bold]Matter:[/bold] {matter_id}\n"
        f"[bold]Status:[/bold] [{color}]{current}[/{color}]\n\n"
        f"{stages_display}\n\n"
        f"[dim]Update: lex contract lifecycle {matter_id} --status <stage>[/dim]",
        title="[bold cyan]Contract Lifecycle[/bold cyan]",
        border_style=color,
    ))


# ---------------------------------------------------------------------------
# lex start — interactive entry point
# ---------------------------------------------------------------------------

@app.command()
def start() -> None:
    """
    Interactive entry point — choose what you want to do.

    Shows a menu to launch research, drafting, contract workspace,
    KB query, or matter management. The fastest way to get started.
    """
    from rich.align import Align

    console.print()
    console.print(Panel(
        Align.center(
            "[bold cyan]⚖ Themis[/bold cyan]\n"
            "[dim]AI agent for Indian litigation. Global. Open-source.[/dim]"
        ),
        border_style="cyan",
        padding=(1, 4),
    ))
    console.print()

    _MENU = [
        ("1", "📝  Draft a legal document",      "lex draft \"your matter brief\""),
        ("2", "🔍  Research case law",            "lex research \"your query\""),
        ("3", "📋  Contract workspace",           "lex contract review / draft / playbook"),
        ("4", "🗄   Query knowledge base",         "lex query \"what to find\""),
        ("5", "🗂   Matter management",            "lex matter list / show"),
        ("6", "🤖  Agent personas",               "lex agent list / create"),
        ("7", "⚙   Setup & config",              "lex setup  ·  lex config"),
    ]

    menu_table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    menu_table.add_column("Num", style="bold cyan", width=3)
    menu_table.add_column("Action", style="bold", min_width=30)
    menu_table.add_column("Command", style="dim")
    for num, action, cmd in _MENU:
        menu_table.add_row(num, action, cmd)

    console.print(menu_table)
    console.print()

    choice = Prompt.ask(
        "[bold cyan]Choose[/bold cyan] [dim](1–7, or q to quit)[/dim]",
        console=console,
    ).strip().lower()

    if choice == "q":
        console.print("[dim]Goodbye.[/dim]")
        raise typer.Exit(0)

    if choice == "1":
        brief = Prompt.ask("[bold cyan]Matter brief[/bold cyan]", console=console)
        if brief.strip():
            draft(brief=brief)
    elif choice == "2":
        q = Prompt.ask("[bold cyan]Research query[/bold cyan]", console=console)
        if q.strip():
            research(brief=q)
    elif choice == "3":
        console.print()
        console.print("[bold cyan]Contract workspace commands:[/bold cyan]")
        console.print("  [bold]lex contract review <file.pdf>[/bold]  — risk analysis + clause flags")
        console.print("  [bold]lex contract draft \"brief\"[/bold]     — draft with firm playbook")
        console.print("  [bold]lex contract playbook list[/bold]      — view firm positions")
        console.print("  [bold]lex contract lifecycle <matter-id>[/bold] — track contract status")
    elif choice == "4":
        q = Prompt.ask("[bold cyan]KB search query[/bold cyan]", console=console)
        if q.strip():
            query(question=q)
    elif choice == "5":
        matter_list()
    elif choice == "6":
        agent_list()
    elif choice == "7":
        config()
    else:
        console.print(f"[yellow]Unknown option: {choice}[/yellow]")


# ---------------------------------------------------------------------------
# lex wisdom — view accumulated practice knowledge
# ---------------------------------------------------------------------------

@app.command()
def wisdom() -> None:
    """
    Show accumulated practice wisdom extracted from past completed drafts.

    Each matter you complete adds 2-4 reusable insights (effective arguments,
    relevant statutes, court-specific notes) to ~/.themis/wisdom.md.
    """
    cfg = LexConfig()
    from themis.memory.wisdom import wisdom_path, load_wisdom

    p = wisdom_path(cfg.home_dir)
    raw = load_wisdom(cfg.home_dir)

    if not raw:
        console.print(Panel(
            "No wisdom accumulated yet.\n\n"
            "Complete a few [bold]lex draft[/bold] runs and insights will appear here automatically.",
            title="[bold cyan]Practice Wisdom[/bold cyan]",
            border_style="cyan",
        ))
        return

    import yaml
    try:
        entries = yaml.safe_load(raw)
    except Exception:
        entries = None

    if not isinstance(entries, list):
        console.print(Panel(raw, title="[bold cyan]Practice Wisdom[/bold cyan]", border_style="cyan"))
        return

    table = Table(title="Practice Wisdom", border_style="cyan", show_lines=True)
    table.add_column("Date", style="dim", width=12)
    table.add_column("Matter Type", style="bold cyan", width=20)
    table.add_column("Jurisdiction", style="blue", width=18)
    table.add_column("Insight", style="white")

    for e in entries:
        if not isinstance(e, dict):
            continue
        table.add_row(
            e.get("date", ""),
            e.get("matter_type", ""),
            e.get("jurisdiction", ""),
            e.get("note", ""),
        )

    console.print(table)
    console.print(f"\n[dim]Source: {p}[/dim]")


# ---------------------------------------------------------------------------
# lex worker — 24/7 living-agent background worker
# ---------------------------------------------------------------------------

@app.command(name="worker")
def worker_cmd(
    poll_interval: float = typer.Option(5.0, "--poll", help="Seconds between job queue polls."),
    session_cap: float = typer.Option(0.0, "--session-cap", help="USD hard cap for the whole session (0 = unlimited)."),
    job_cap: float = typer.Option(0.0, "--job-cap", help="USD hard cap per individual job (0 = unlimited)."),
    idle_timeout: int = typer.Option(0, "--idle-timeout", help="Cancel job if no LLM activity for N minutes (0 = off)."),
    max_jobs: int = typer.Option(0, "--max-jobs", help="Stop after processing N jobs (0 = run forever, useful for tests)."),
) -> None:
    """
    Start the Themis living-agent worker.

    Polls the Postgres job queue and processes jobs: document ingestion,
    fact extraction, chronology building, deadline scans, morning briefs,
    and draft generation.

    Requires LEX_POSTGRES_URL (or DATABASE_URL) to be set.
    The worker stops cleanly on Ctrl-C.
    """
    import asyncio

    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    try:
        from themis.config import LexConfig
        cfg = LexConfig()
        if not cfg.postgres_url:
            console.print("[bold red]Error:[/bold red] LEX_POSTGRES_URL / DATABASE_URL not set.")
            raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    # Import job handlers to register them before starting the worker
    import themis.runtime.jobs  # noqa: F401

    from themis.runtime.postgres import PostgresRuntimeRepository
    from themis.runtime.worker import RuntimeWorker

    repo = PostgresRuntimeRepository(cfg.postgres_url)
    repo.setup()

    worker = RuntimeWorker(
        repo=repo,
        poll_interval=poll_interval,
        session_cap_usd=session_cap,
        job_cap_usd=job_cap,
        idle_timeout_minutes=idle_timeout,
    )

    console.print(Panel(
        f"[bold green]Themis Worker started[/bold green]\n"
        f"Poll interval: {poll_interval}s | "
        f"Session cap: {'$' + str(session_cap) if session_cap else 'unlimited'} | "
        f"Job cap: {'$' + str(job_cap) if job_cap else 'unlimited'}\n"
        f"Press [bold]Ctrl-C[/bold] to stop.",
        border_style="green",
        padding=(0, 2),
    ))

    try:
        asyncio.run(worker.run(max_jobs=max_jobs if max_jobs > 0 else None))
    except KeyboardInterrupt:
        console.print("\n[dim]Worker stopped.[/dim]")


# ---------------------------------------------------------------------------
# lex help — rich reference card
# ---------------------------------------------------------------------------

@app.command(name="help")
def help_cmd() -> None:
    """
    Show a full reference card of all Themis commands and usage examples.
    """
    from rich.columns import Columns

    console.print()
    console.print(Panel(
        "[bold cyan]⚖ Themis[/bold cyan] — AI agent for Indian litigation\n"
        "[dim]Global. Open-source. Self-improving.[/dim]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()

    _SECTIONS = [
        (
            "🚀  Getting Started",
            "cyan",
            [
                ("lex start",                       "Interactive menu — choose what to do"),
                ("lex setup",                       "First-run wizard — create your lawyer profile"),
                ("lex config",                      "Show current model, paths, and toggles"),
            ],
        ),
        (
            "📝  Drafting",
            "green",
            [
                ("lex draft \"brief\"",             "Draft a legal document from a matter brief"),
                ("lex draft \"@vikram brief\"",     "Draft using a specific agent persona"),
                ("lex draft --agent priya \"brief\"","Draft with --agent flag"),
                ("lex draft -m M-ABCD1234",         "Resume / continue an existing matter"),
                ("lex draft -o output.docx",        "Export draft to .docx file"),
            ],
        ),
        (
            "🔍  Research",
            "blue",
            [
                ("lex research \"query\"",          "Research case law only — no draft produced"),
                ("lex research --save",             "Save research findings to matter memory"),
                ("lex query \"search term\"",       "Search KB across all past matter research"),
                ("lex query -n 20",                 "Return up to 20 KB results"),
                ("lex search \"keyword\"",          "Full-text search across all saved sessions"),
            ],
        ),
        (
            "📋  Contracts",
            "yellow",
            [
                ("lex contract review file.pdf",    "AI risk analysis + clause flags"),
                ("lex contract review -p nda",      "Review with NDA firm playbook applied"),
                ("lex contract review -o report.md","Save risk report to file"),
                ("lex contract draft \"brief\"",    "Draft a contract with playbook positions"),
                ("lex contract playbook list",      "List all firm playbooks"),
                ("lex contract playbook show <id>", "Show clause positions in a playbook"),
                ("lex contract playbook add",       "Create a new playbook interactively"),
                ("lex contract lifecycle <id>",     "View contract lifecycle status"),
                ("lex contract lifecycle -s executed","Update lifecycle stage"),
            ],
        ),
        (
            "🤖  Agent Personas",
            "magenta",
            [
                ("lex agent list",                  "List all bundled + custom agents"),
                ("lex agent show vikram",           "Show agent persona details"),
                ("lex agent create",                "Create a custom agent interactively"),
                ("lex agent delete <id>",           "Delete a custom agent"),
                ("@vikram in any brief",            "Invoke agent via @mention"),
            ],
        ),
        (
            "🗂   Matters & Memory",
            "cyan",
            [
                ("lex matter list",                 "List all saved matters"),
                ("lex matter show M-ABCD1234",      "Show matter memory log"),
                ("lex reminder add -m M-ABCD1234",  "Set a hearing reminder"),
                ("lex reminder list",               "List pending reminders"),
            ],
        ),
        (
            "🌐  Gateways",
            "dim",
            [
                ("lex gateway telegram",            "Start Telegram bot gateway"),
                ("lex gateway web",                 "Start REST API / control plane"),
                ("lex voice",                       "Start Voice AI gateway"),
                ("lex voice --twilio",              "Show Twilio webhook config"),
            ],
        ),
    ]

    for section_title, color, commands in _SECTIONS:
        console.print(Rule(title=f"[bold {color}] {section_title} [/bold {color}]", style=color))
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column("Command", style=f"bold {color}", min_width=36)
        t.add_column("Description", style="dim")
        for cmd, desc in commands:
            t.add_row(cmd, desc)
        console.print(t)
        console.print()

    console.print(Panel(
        "[dim]Docs:[/dim] [bold]https://github.com/your-org/themis[/bold]\n"
        "[dim]Issues:[/dim] Use GitHub Issues\n"
        "[dim]First time?[/dim] Run [bold cyan]lex setup[/bold cyan] then [bold cyan]lex start[/bold cyan]",
        border_style="dim",
        padding=(0, 2),
    ))
    console.print()


@app.command("grid")
def grid_cmd(
    matter_id: str = typer.Argument(..., help="Matter ID to run grid against."),
    questions: Optional[List[str]] = typer.Option(
        None, "--questions", "-q",
        help="Question to run across all documents. Repeat for multiple.",
    ),
    output_csv: Optional[str] = typer.Option(None, "--csv", help="Write results to CSV file."),
) -> None:
    """Run a question grid across all documents in a matter."""
    import csv as csv_mod
    from themis.nodes.grid import run as grid_run

    if not questions:
        console.print("[red]At least one --questions/-q is required.[/red]")
        raise typer.Exit(1)

    result = asyncio.run(grid_run({
        "matter_id": matter_id,
        "grid_questions": questions,
        "messages": [],
        "error": None,
    }))
    grid = result.get("grid_results") or {}
    if not grid:
        console.print("[yellow]No results — check that documents exist in the matter docs folder.[/yellow]")
        raise typer.Exit(1)

    docs = sorted({d for row in grid.values() for d in row})
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Question", style="bold", max_width=40)
    for doc in docs:
        table.add_column(doc, max_width=30)
    for question, row in grid.items():
        table.add_row(question, *[row.get(d, "") for d in docs])
    console.print(table)

    if output_csv:
        with open(output_csv, "w", newline="") as f:
            w = csv_mod.writer(f)
            w.writerow(["Question"] + docs)
            for question, row in grid.items():
                w.writerow([question] + [row.get(d, "") for d in docs])
        console.print(f"[green]Saved to {output_csv}[/green]")


if __name__ == "__main__":
    app()
