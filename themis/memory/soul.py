# WHY: SOUL.md is the lawyer's persistent identity file.
# It lives at ~/.themis/SOUL.md so it survives project updates and is never committed to git.
# The draft node reads it and injects it into every system prompt so every document
# reflects the lawyer's name, bar details, court preferences, and drafting style.

import random
import re
import time
from pathlib import Path
from typing import Optional

import yaml
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console()

SOUL_FILENAME = "SOUL.md"

SOUL_TEMPLATE = """\
# Lawyer Identity

**Name:** {name}
**Bar Enrollment:** {bar_enrollment}
**Practice Since:** {practice_since}

## Practice Profile
**Primary Courts:** {primary_courts}
**Primary Practice Areas:** {practice_areas}
**Typical Matter Types:** {matter_types}

## Drafting Style
**Preferred Tone:** {tone}
**Citation Preference:** {citation_preference}
**Document Length:** {doc_length}
**Language Notes:** {language_notes}

## Document Formatting
**Formatting Style:** {formatting_style}

## Firm Context
**Firm Name:** {firm_name}
**Firm Type:** {firm_type}

## Known Judicial Preferences
{judicial_preferences}

## Custom Instructions
{custom_instructions}
"""


def soul_path(home_dir: str = "~/.themis") -> Path:
    return Path(home_dir).expanduser() / SOUL_FILENAME


def load_soul(home_dir: str = "~/.themis") -> Optional[dict]:
    path = soul_path(home_dir)
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    return _parse_soul(content)


def save_soul(soul_data: dict, home_dir: str = "~/.themis") -> Path:
    path = soul_path(home_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = SOUL_TEMPLATE.format(
        name=soul_data.get("name", ""),
        bar_enrollment=soul_data.get("bar_enrollment", ""),
        practice_since=soul_data.get("practice_since", ""),
        primary_courts=soul_data.get("primary_courts", ""),
        practice_areas=soul_data.get("practice_areas", ""),
        matter_types=soul_data.get("matter_types", ""),
        tone=soul_data.get("tone", "Senior formal"),
        citation_preference=soul_data.get("citation_preference", "Always include"),
        doc_length=soul_data.get("doc_length", "Comprehensive"),
        language_notes=soul_data.get("language_notes", ""),
        formatting_style=soul_data.get("formatting_style", "district_court"),
        firm_name=soul_data.get("firm_name", ""),
        firm_type=soul_data.get("firm_type", ""),
        judicial_preferences=soul_data.get("judicial_preferences", ""),
        custom_instructions=soul_data.get("custom_instructions", ""),
    )
    path.write_text(content, encoding="utf-8")
    return path


def append_soul_note(note: str, section: str = "Custom Instructions", home_dir: str = "~/.themis") -> None:
    path = soul_path(home_dir)
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8")
    pattern = rf"(## {re.escape(section)}\n)(.*?)(\n## |\Z)"
    replacement = lambda m: m.group(1) + m.group(2).rstrip() + f"\n- {note}\n" + m.group(3)
    updated = re.sub(pattern, replacement, content, flags=re.DOTALL)
    if updated == content:
        updated = content.rstrip() + f"\n\n## {section}\n- {note}\n"
    path.write_text(updated, encoding="utf-8")


# ---------------------------------------------------------------------------
# Trivia helper
# ---------------------------------------------------------------------------

_TRIVIA_CACHE: list[dict] = []


def _load_trivia() -> list[dict]:
    global _TRIVIA_CACHE
    if _TRIVIA_CACHE:
        return _TRIVIA_CACHE
    try:
        trivia_path = Path(__file__).parent.parent / "data" / "legal_trivia.yaml"
        data = yaml.safe_load(trivia_path.read_text(encoding="utf-8"))
        _TRIVIA_CACHE = data.get("trivia", [])
    except Exception:
        _TRIVIA_CACHE = []
    return _TRIVIA_CACHE


def _show_trivia() -> None:
    """Display a random Indian legal trivia fact — called between wizard steps."""
    trivia = _load_trivia()
    if not trivia:
        return
    item = random.choice(trivia)
    fact = item.get("fact", "")
    category = item.get("category", "Legal Trivia")

    console.print()
    console.print(
        Panel(
            f"[italic]{fact}[/italic]",
            title=f"[bold yellow]⚖ Legal Trivia — {category}[/bold yellow]",
            border_style="yellow",
            padding=(0, 2),
        )
    )
    console.print()


def _fake_progress(label: str, seconds: float = 1.2) -> None:
    """Show a brief animated progress bar — used during 'saving' moments."""
    with Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn(f"[cyan]{label}[/cyan]"),
        BarColumn(bar_width=30, complete_style="cyan", finished_style="green"),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("", total=100)
        steps = 20
        for i in range(steps):
            time.sleep(seconds / steps)
            progress.update(task, advance=100 / steps)


# ---------------------------------------------------------------------------
# Beautiful setup wizard
# ---------------------------------------------------------------------------

def run_setup_wizard(home_dir: str = "~/.themis") -> dict:
    """
    Interactive CLI setup wizard — redesigned for beauty and delight.
    Shows legal trivia between steps so the lawyer is never bored.
    """
    console.print()
    console.print(Rule(style="cyan"))
    console.print()

    # Header splash
    header = Text()
    header.append("  ⚖  ", style="bold cyan")
    header.append("THEMIS", style="bold white")
    header.append("  —  AI Agent for Indian Litigation\n", style="dim white")
    header.append("  Setting up your lawyer profile", style="cyan")
    console.print(Align.center(header))
    console.print()
    console.print(Rule(style="cyan"))
    console.print()

    console.print(
        Panel(
            "[bold]This 2-minute wizard creates your[/bold] [cyan]SOUL.md[/cyan] [bold]file.[/bold]\n\n"
            "Every draft Themis produces will reflect your name, court, style, and preferences.\n"
            "Think of it as briefing Themis on who you are — once.\n\n"
            "[dim]Press Enter to skip any field.  All fields can be edited later at [cyan]~/.themis/SOUL.md[/cyan][/dim]",
            border_style="cyan",
            padding=(1, 3),
        )
    )
    console.print()

    # Step tracker
    total_steps = 8
    step = [0]

    def _step_header(title: str, subtitle: str = "") -> None:
        step[0] += 1
        console.print()
        console.print(Rule(
            title=f"[bold cyan] Step {step[0]} of {total_steps} — {title} [/bold cyan]",
            style="cyan",
        ))
        if subtitle:
            console.print(f"  [dim]{subtitle}[/dim]")
        console.print()

    def ask(prompt_text: str, hint: str = "", default: str = "") -> str:
        if hint:
            console.print(f"  [dim]{hint}[/dim]")
        val = Prompt.ask(f"  [bold cyan]›[/bold cyan] {prompt_text}", default=default, console=console)
        return val.strip()

    # --- Step 1: Identity ---
    _step_header("Your Identity", "How you appear on court documents and vakalatnamas.")
    name = ask("Full name", "As enrolled with the Bar Council (e.g. Arjun Kapoor)")
    bar_enrollment = ask("Bar enrollment number", "Format varies by state — e.g. D/123/2010 or MH/456/2015")
    practice_since = ask("Year called to the Bar", "E.g. 2010 or 2018")

    _show_trivia()

    # --- Step 2: Practice profile ---
    _step_header("Your Practice", "Tells Themis which courts and matters you typically handle.")

    # Court selection table
    _courts = [
        ("SC", "Supreme Court of India"),
        ("DHC", "Delhi High Court"),
        ("BHC", "Bombay High Court"),
        ("MHC", "Madras High Court"),
        ("CHC", "Calcutta High Court"),
        ("KHC", "Karnataka High Court"),
        ("Other", "Other / District Court"),
    ]
    court_table = Table(show_header=False, box=None, padding=(0, 2))
    court_table.add_column("Code", style="bold cyan")
    court_table.add_column("Court")
    for code, name_court in _courts:
        court_table.add_row(code, name_court)
    console.print("  [dim]Common courts (type the code or any custom name):[/dim]")
    console.print(court_table)
    console.print()
    primary_courts = ask(
        "Primary courts",
        "You can list multiple separated by commas (e.g. DHC, Saket District Court)",
    )

    practice_areas = ask(
        "Primary practice areas",
        "E.g. Civil Litigation, Arbitration, Intellectual Property, Criminal, Corporate",
    )
    matter_types = ask(
        "Typical matter types",
        "E.g. injunctions, recovery suits, writs, contracts, bail applications, opinions",
    )

    _show_trivia()

    # --- Step 3: Drafting style ---
    _step_header("Your Drafting Style", "Shapes how Themis writes — tone, length, citations.")

    _tones = ["Senior formal", "Accessible English", "Aggressive", "Conciliatory", "Plain commercial"]
    tone_table = Table(show_header=False, box=None, padding=(0, 2))
    tone_table.add_column("#", style="bold cyan", width=3)
    tone_table.add_column("Style")
    for i, t in enumerate(_tones, 1):
        tone_table.add_row(str(i), t)
    console.print("  [dim]Tone options (type number or your own):[/dim]")
    console.print(tone_table)
    console.print()
    tone_raw = ask("Preferred drafting tone", default="1")
    try:
        tone = _tones[int(tone_raw) - 1]
    except (ValueError, IndexError):
        tone = tone_raw or "Senior formal"

    citation_preference = ask(
        "Citation preference",
        "Options: Always include  /  Only when critical  /  Ask each time",
        default="Always include",
    )
    doc_length = ask(
        "Document length",
        "Comprehensive (detailed and exhaustive) or Concise",
        default="Comprehensive",
    )
    language_notes = ask(
        "Language notes",
        "E.g. 'avoid legalese in client letters' or 'include Hindi summary'",
        default="",
    )

    _show_trivia()

    # --- Step 4: Firm ---
    _step_header("Your Firm", "Used in document headers and correspondence.")
    firm_name = ask("Firm name", "Leave blank if solo practitioner", default="")
    firm_type = ask("Firm type", "Solo  /  Small firm  /  Large firm", default="Solo")

    _show_trivia()

    # --- Step 5: Court preferences ---
    _step_header(
        "Judicial Preferences",
        "Notes about how your bench likes arguments — purely for drafting intelligence.",
    )
    judicial_preferences = ask(
        "Known judicial preferences",
        "E.g. 'Bench 5 prefers concise prayers' or 'judge dislikes latin maxims'",
        default="",
    )

    _show_trivia()

    # --- Step 6: Custom instructions ---
    _step_header("Custom Instructions", "Tell Themis anything else it should always remember.")
    custom_instructions = ask(
        "Any other standing instructions",
        "Red-lines, non-obvious preferences, client confidentiality notes, etc.",
        default="",
    )

    _show_trivia()

    # --- Step 7: Formatting style ---
    _step_header(
        "Document Formatting Style",
        "Controls font, paper size, and spacing for all generated court documents.",
    )

    from themis.courts import FORMATTING_PRESET_LABELS

    fmt_options = list(FORMATTING_PRESET_LABELS.items())  # [(key, label), ...]
    fmt_table = Table(show_header=False, box=None, padding=(0, 2))
    fmt_table.add_column("#", style="bold cyan", width=3)
    fmt_table.add_column("Label")
    for i, (_, label) in enumerate(fmt_options, 1):
        fmt_table.add_row(str(i), label)
    console.print("  [dim]Formatting presets:[/dim]")
    console.print(fmt_table)
    console.print()
    fmt_raw = ask(
        "Formatting style",
        "Choose number — or press Enter for District Court (default)",
        default="1",
    )
    try:
        fmt_idx = int(fmt_raw) - 1
        formatting_style = fmt_options[fmt_idx][0] if 0 <= fmt_idx < len(fmt_options) else "district_court"
    except (ValueError, IndexError):
        formatting_style = fmt_raw.lower().replace(" ", "_") or "district_court"

    _show_trivia()

    # --- Step 8: Agent persona ---
    _step_header("Choose Your Default Agent", "Themis ships with 4 built-in advocate personas. You can create custom ones with `lex agent create`.")

    from themis.agents.registry import list_agents
    from themis.agents.faces import FACES

    all_agents = list_agents()
    agent_table = Table(show_header=True, box=None, padding=(0, 2), border_style="cyan")
    agent_table.add_column("#", style="bold cyan", width=3)
    agent_table.add_column("Handle", style="bold")
    agent_table.add_column("Name")
    agent_table.add_column("Tagline", style="dim")
    for i, ag in enumerate(all_agents, 1):
        agent_table.add_row(str(i), f"@{ag['id']}", ag["name"], ag.get("tagline", ""))
    console.print(agent_table)
    console.print()
    agent_raw = ask(
        "Default agent (number or handle, or press Enter to skip)",
        "You can always switch with @agentname in your brief",
        default="",
    )
    default_agent_id = ""
    if agent_raw:
        try:
            idx = int(agent_raw) - 1
            if 0 <= idx < len(all_agents):
                default_agent_id = all_agents[idx]["id"]
        except ValueError:
            default_agent_id = agent_raw.lstrip("@").lower()

    soul_data = {
        "name": name,
        "bar_enrollment": bar_enrollment,
        "practice_since": practice_since,
        "primary_courts": primary_courts,
        "practice_areas": practice_areas,
        "matter_types": matter_types,
        "tone": tone,
        "citation_preference": citation_preference,
        "doc_length": doc_length,
        "language_notes": language_notes,
        "formatting_style": formatting_style,
        "firm_name": firm_name,
        "firm_type": firm_type,
        "judicial_preferences": judicial_preferences,
        "custom_instructions": custom_instructions,
        "default_agent": default_agent_id,
    }

    # Save with animated progress bar
    console.print()
    _fake_progress("Saving your profile...", seconds=1.0)

    path = save_soul(soul_data, home_dir)

    # Show the selected agent face if chosen
    if default_agent_id:
        from themis.agents.registry import load_agent
        agent = load_agent(default_agent_id)
        if agent:
            face_key = agent.get("face", "sharp_counsel")
            face = FACES.get(face_key, FACES["sharp_counsel"])
            console.print()
            console.print(
                Panel(
                    f"[bold cyan]{face['art']}[/bold cyan]\n"
                    f"[bold]@{agent['id']}[/bold] — {agent.get('name', '')}\n"
                    f"[dim]{agent.get('tagline', '')}[/dim]",
                    title=f"[bold green]Your default agent[/bold green]",
                    border_style="green",
                    padding=(0, 2),
                )
            )

    console.print()
    console.print(Rule(style="green"))
    console.print()

    # Summary panel
    summary_rows = [
        ("Name", name or "—"),
        ("Bar enrollment", bar_enrollment or "—"),
        ("Courts", primary_courts or "—"),
        ("Practice areas", practice_areas or "—"),
        ("Tone", tone),
        ("Formatting style", formatting_style),
        ("Firm", firm_name or "Solo"),
        ("Default agent", f"@{default_agent_id}" if default_agent_id else "None"),
    ]
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Field", style="bold cyan", no_wrap=True)
    summary_table.add_column("Value")
    for field, value in summary_rows:
        summary_table.add_row(field, value)

    console.print(
        Panel(
            summary_table,
            title="[bold green]✓ Setup Complete — Your Profile[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()
    console.print(
        f"[dim]Saved to [cyan]{path}[/cyan]\n"
        "Edit any time to update your profile.\n"
        "Run [bold]lex agent create[/bold] to build a custom agent persona.[/dim]"
    )
    console.print()
    console.print(Rule(style="cyan"))
    console.print()

    # Research tools setup — runs immediately after profile save
    _setup_research_tools(home_dir)
    console.print()

    # Guided demo offer
    offer = Prompt.ask(
        "  [bold]Want a quick demo draft?[/bold] [dim](shows how Themis would handle your first matter)[/dim]",
        choices=["y", "n"],
        default="n",
        console=console,
    )
    if offer.lower() == "y":
        console.print()
        console.print(
            Panel(
                "You'll see exactly the flow a lawyer goes through:\n"
                "  1. Themis asks clarifying questions\n"
                "  2. It researches Indian case law\n"
                "  3. It drafts and verifies citations\n\n"
                "Run [bold cyan]lex draft[/bold cyan] with any matter brief to start for real.",
                title="[bold blue]How It Works[/bold blue]",
                border_style="blue",
                padding=(1, 2),
            )
        )

    return soul_data


# ---------------------------------------------------------------------------
# Research tools setup wizard
# ---------------------------------------------------------------------------

_RESEARCH_TOOLS = [
    # (display_label, env_key_flag, env_key_api, needs_key, dashboard_hint)
    ("Indian Kanoon API",   "LEX_ENABLE_KANOON",        "KANOON_API_KEY",         True,  None),
    ("eCourts MCP",         "LEX_ECOURTS_BACKEND=api",  "ECOURTS_API_KEY",         True,  "https://api.ecourts.gov.in/dashboard  (Register → My Applications → Create API Key)"),
    ("legislation.gov.in",  "LEX_LEGISLATION_ENABLED",  None,                      False, None),
    ("Playwright browser",  "LEX_PLAYWRIGHT_ENABLED",   None,                      False, None),
    ("Tavily",              "LEX_TAVILY_ENABLED",        "TAVILY_API_KEY",          True,  None),
    ("SerpAPI",             "LEX_SERPAPI_ENABLED",       "SERPAPI_API_KEY",         True,  None),
    ("Perplexity",          "LEX_PERPLEXITY_ENABLED",    "PERPLEXITY_API_KEY",      True,  None),
    ("DuckDuckGo",          "LEX_WEB_SEARCH_ENABLED",   None,                      False, None),
    ("Jina Reader",         "LEX_JINA_ENABLED",         None,                      False, None),
    ("Firecrawl",           "LEX_FIRECRAWL_ENABLED",    "FIRECRAWL_API_KEY",       True,  None),
    ("CourtListener (US)",  "LEX_COURTLISTENER_ENABLED","COURTLISTENER_API_KEY",   True,  None),
]


def _setup_research_tools(home_dir: str = "~/.themis") -> None:
    """
    Interactive terminal wizard for configuring research tools.
    Writes LEX_* flags and API keys to ~/.themis/.env.
    Called from run_setup_wizard() and `lex config tools`.
    """
    import getpass

    console.print(Rule("[bold cyan]Research Tools Setup[/bold cyan]", style="cyan"))
    console.print()
    console.print("  [bold]Available research tools[/bold] (all off by default):\n")
    console.print("  [dim]— Indian case law —[/dim]")
    console.print("  [bold cyan] 1[/bold cyan]  Indian Kanoon API      [dim](requires KANOON_API_KEY)[/dim]")
    console.print("  [bold cyan] 2[/bold cyan]  eCourts MCP            [dim](requires ECOURTS_API_KEY from eCourts dashboard)[/dim]")
    console.print("  [bold cyan] 3[/bold cyan]  legislation.gov.in     [dim](no key — official statute portal)[/dim]")
    console.print("  [bold cyan] 4[/bold cyan]  Playwright browser     [dim](no key — scrapes Kanoon directly)[/dim]")
    console.print()
    console.print("  [dim]— Web search —[/dim]")
    console.print("  [bold cyan] 5[/bold cyan]  Tavily                 [dim](requires TAVILY_API_KEY)[/dim]")
    console.print("  [bold cyan] 6[/bold cyan]  SerpAPI                [dim](requires SERPAPI_API_KEY)[/dim]")
    console.print("  [bold cyan] 7[/bold cyan]  Perplexity             [dim](requires PERPLEXITY_API_KEY)[/dim]")
    console.print("  [bold cyan] 8[/bold cyan]  DuckDuckGo             [dim](no key — free web search)[/dim]")
    console.print()
    console.print("  [dim]— Verification —[/dim]")
    console.print("  [bold cyan] 9[/bold cyan]  Jina Reader            [dim](no key — verifies citation URLs)[/dim]")
    console.print("  [bold cyan]10[/bold cyan]  Firecrawl              [dim](requires FIRECRAWL_API_KEY)[/dim]")
    console.print()
    console.print("  [dim]— International —[/dim]")
    console.print("  [bold cyan]11[/bold cyan]  CourtListener (US)     [dim](requires COURTLISTENER_API_KEY, scaffold only)[/dim]")
    console.print()

    raw = Prompt.ask(
        "  Select tools to enable [dim](e.g. 1,3,5,9 — or 0 to skip)[/dim]",
        default="0",
        console=console,
    ).strip()

    if raw == "0":
        console.print("  [dim]⏭  Research tools skipped — run [bold]lex config tools[/bold] to configure later.[/dim]")
        return

    # Parse selection
    selected_indices: list[int] = []
    for part in raw.split(","):
        try:
            idx = int(part.strip()) - 1
            if 0 <= idx < len(_RESEARCH_TOOLS):
                selected_indices.append(idx)
        except ValueError:
            pass

    if not selected_indices:
        console.print("  [yellow]No valid selection — skipping.[/yellow]")
        return

    env_lines: list[str] = []

    for idx in selected_indices:
        label, flag_key, api_key_name, needs_key, dashboard_hint = _RESEARCH_TOOLS[idx]
        console.print()
        console.print(f"  [bold green]✓[/bold green] Enabling [bold]{label}[/bold]")

        # Write the boolean/backend flag
        if flag_key == "LEX_ECOURTS_BACKEND=api":
            env_lines.append("LEX_ECOURTS_BACKEND=api")
        else:
            env_lines.append(f"{flag_key}=true")

        if needs_key and api_key_name:
            if dashboard_hint:
                console.print(f"  [bold blue]ℹ[/bold blue]  Get your API key at: [link]{dashboard_hint}[/link]")
            api_key_val = getpass.getpass(f"    Enter {label} API key (hidden): ").strip()
            if api_key_val:
                env_lines.append(f"{api_key_name}={api_key_val}")
                console.print("  [green]  Key saved (not displayed for security).[/green]")
            else:
                console.print(f"  [yellow]  No key entered — {label} enabled but key missing.[/yellow]")

    # Write to ~/.themis/.env
    if env_lines:
        lex_env = Path(home_dir).expanduser() / ".env"
        existing = lex_env.read_text(encoding="utf-8") if lex_env.exists() else ""
        new_entries = [line for line in env_lines if line.split("=")[0] not in existing]
        if new_entries:
            with lex_env.open("a", encoding="utf-8") as f:
                f.write(("\n" if existing and not existing.endswith("\n") else "") + "\n".join(new_entries) + "\n")

    console.print()
    console.print(
        f"  [green]✓[/green] Research tools configured — "
        f"{len(selected_indices)} tool(s) enabled. "
        f"Settings saved to [cyan]{Path(home_dir).expanduser() / '.env'}[/cyan]"
    )


# ---------------------------------------------------------------------------
# Internal parser
# ---------------------------------------------------------------------------

def _parse_soul(content: str) -> dict:
    soul: dict = {"raw": content}
    for match in re.finditer(r"\*\*(.+?):\*\*\s*(.+)", content):
        key = match.group(1).strip().lower().replace(" ", "_")
        value = match.group(2).strip()
        soul[key] = value
    for match in re.finditer(r"## (.+?)\n(.*?)(?=\n## |\Z)", content, re.DOTALL):
        section_name = match.group(1).strip().lower().replace(" ", "_")
        section_body = match.group(2).strip()
        soul[f"section_{section_name}"] = section_body
    soul.setdefault("name", soul.get("name", ""))
    soul.setdefault("bar_enrollment", soul.get("bar_enrollment", ""))
    return soul
