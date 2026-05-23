# WHY: SOUL.md is the lawyer's persistent identity file.
# It lives at ~/.lexagent/SOUL.md so it survives project updates and is never committed to git.
# The draft node reads it and injects it into every system prompt so every document
# reflects the lawyer's name, bar details, court preferences, and drafting style.
#
# The Hermes Agent pattern: a "soul" or "persona" file that shapes agent behaviour
# across all sessions — loaded once, used everywhere.

import re
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()

# The canonical location of the lawyer's soul file.
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

## Firm Context
**Firm Name:** {firm_name}
**Firm Type:** {firm_type}

## Known Judicial Preferences
{judicial_preferences}

## Custom Instructions
{custom_instructions}
"""


def soul_path(home_dir: str = "~/.lexagent") -> Path:
    """Returns the absolute Path to the SOUL.md file."""
    return Path(home_dir).expanduser() / SOUL_FILENAME


def load_soul(home_dir: str = "~/.lexagent") -> Optional[dict]:
    """
    Load the lawyer's SOUL.md into a dict.

    Returns None if the file does not exist (first run).
    Returns a dict with keys matching the sections in SOUL_TEMPLATE:
      name, bar_enrollment, practice_since, primary_courts, practice_areas,
      matter_types, tone, citation_preference, doc_length, language_notes,
      firm_name, firm_type, judicial_preferences, custom_instructions, raw
    """
    path = soul_path(home_dir)
    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    return _parse_soul(content)


def save_soul(soul_data: dict, home_dir: str = "~/.lexagent") -> Path:
    """
    Write SOUL.md from a dict of soul fields.
    Creates ~/.lexagent/ if it does not exist.
    Returns the path where it was saved.
    """
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
        firm_name=soul_data.get("firm_name", ""),
        firm_type=soul_data.get("firm_type", ""),
        judicial_preferences=soul_data.get("judicial_preferences", ""),
        custom_instructions=soul_data.get("custom_instructions", ""),
    )
    path.write_text(content, encoding="utf-8")
    return path


def append_soul_note(note: str, section: str = "Custom Instructions", home_dir: str = "~/.lexagent") -> None:
    """
    Append a note to a specific section of SOUL.md.
    Used by the self-learning loop (Phase 6) to record preferences from completed matters.
    """
    path = soul_path(home_dir)
    if not path.exists():
        return

    content = path.read_text(encoding="utf-8")

    # Find the section header and append after it
    pattern = rf"(## {re.escape(section)}\n)(.*?)(\n## |\Z)"
    replacement = lambda m: m.group(1) + m.group(2).rstrip() + f"\n- {note}\n" + m.group(3)
    updated = re.sub(pattern, replacement, content, flags=re.DOTALL)

    if updated == content:
        # Section not found — append at end
        updated = content.rstrip() + f"\n\n## {section}\n- {note}\n"

    path.write_text(updated, encoding="utf-8")


def run_setup_wizard(home_dir: str = "~/.lexagent") -> dict:
    """
    Interactive CLI wizard that collects lawyer identity and writes SOUL.md.
    Called by `lex setup`. Returns the soul_data dict after saving.
    Now lawyer-friendly: every field has a practical explanation.
    Also offers a guided first matter-intake demo at the end.
    """
    console.print()
    console.print(Panel(
        "Welcome to LexAgent. This 2-minute wizard creates your lawyer profile.\n"
        "It lives at [cyan]~/.lexagent/SOUL.md[/cyan] and personalises every draft.\n\n"
        "[dim]Press Enter to skip any field.[/dim]",
        title="[bold cyan]⚖ LexAgent Setup — Lawyer Profile[/bold cyan]",
        border_style="cyan",
    ))
    console.print()

    def ask_with_explanation(header: str, explanation: str, default: str = "") -> str:
        if explanation:
            console.print(f"[dim]{explanation}[/dim]")
        val = Prompt.ask(f"[bold]{header}[/bold]", default=default, console=console)
        return val.strip()

    soul_data = {
        "name": ask_with_explanation(
            "Your full name",
            "Name, as enrolled with Bar Council or as you prefer on court documents.",
        ),
        "bar_enrollment": ask_with_explanation(
            "Bar enrollment number and state",
            "Include format as required by your jurisdiction, e.g. D/123/2010, Delhi Bar Council.",
        ),
        "practice_since": ask_with_explanation(
            "Year called to the Bar",
            "Which year were you admitted to practice law? E.g., 2010.",
        ),
        "primary_courts": ask_with_explanation(
            "Primary courts you practise in",
            "You can list multiple (e.g. Delhi High Court, Saket District Court).",
        ),
        "practice_areas": ask_with_explanation(
            "Primary practice areas",
            "E.g. Civil Litigation, Arbitration, Intellectual Property, White Collar, etc.",
        ),
        "matter_types": ask_with_explanation(
            "Typical matter types",
            "What kinds of matters do you usually draft? E.g. injunctions, recovery suits, writs, contracts, opinions.",
        ),
        "tone": ask_with_explanation(
            "Preferred drafting tone",
            "Should drafts be 'Senior formal', 'Accessible English', 'Aggressive', 'Conciliatory', etc.?",
            default="Senior formal",
        ),
        "citation_preference": ask_with_explanation(
            "Citation preference",
            "Choose: Always include, Only when critical, or Ask each time.",
            default="Always include",
        ),
        "doc_length": ask_with_explanation(
            "Document length preference",
            "Comprehensive (detailed and exhaustive) or Concise?",
            default="Comprehensive",
        ),
        "language_notes": ask_with_explanation(
            "Any language notes",
            "E.g. avoid legalese in client letters, or include Hindi summaries as well.",
            default="",
        ),
        "firm_name": ask_with_explanation(
            "Firm name (leave blank if solo)",
            "If part of a firm, enter the firm's name; else leave blank.",
            default="",
        ),
        "firm_type": ask_with_explanation(
            "Firm type",
            "Solo, Small firm, or Large firm.",
            default="Solo",
        ),
        "judicial_preferences": ask_with_explanation(
            "Known judicial preferences",
            "E.g. 'Bench 5 prefers concise prayers' or note common expectations in your practice court.",
            default="",
        ),
        "custom_instructions": ask_with_explanation(
            "Any other instructions LexAgent should always follow",
            "Let LexAgent know of quirks, preferences, red-lines, or anything nonstandard.",
            default="",
        ),
    }

    path = save_soul(soul_data, home_dir)

    console.print()
    console.print(Panel(
        f"[green]Profile saved to {path}[/green]\n\n"
        "Every draft will now reference your name, bar details, and style.\n"
        "Edit [cyan]~/.lexagent/SOUL.md[/cyan] any time to update your profile.",
        title="[bold green]✓ Setup Complete[/bold green]",
        border_style="green",
    ))
    console.print()

    offer = Prompt.ask("Would you like a guided demo of drafting your first matter?", choices=["y","n"], default="y", console=console)
    if offer.lower() == "y":
        console.print(Panel(
            "Let's simulate your first matter intake. LexAgent will prompt you just as it would in live use.\n\n"
            "You can use dummy information or a real scenario. This helps you see the flow and what information is needed for best results.",
            title="[bold blue]Guided First Matter Intake[/bold blue]",
            border_style="blue",
        ))
        # EXAMPLE MATTER INTAKE FLOW (stub)
        example_brief = Prompt.ask("Enter a brief for your legal matter (e.g. 'I need an injunction to prevent demolition of my property in Delhi')", default="I need a stay order for property dispute.", console=console)
        # For demo, just show what would happen, don't actually invoke graph.
        console.print("[dim]LexAgent would now proceed to ask clarifying questions, research case law, and prepare your draft based on your profile.\nFor a complete run, use [bold]lex draft[/bold].[/dim]")

    return soul_data


# -----------------------------------------------------------------------
# Internal parser
# -----------------------------------------------------------------------

def _parse_soul(content: str) -> dict:
    """
    Parse a SOUL.md file into a flat dict.
    Also stores the raw text so nodes can inject it verbatim into prompts.
    """
    soul: dict = {"raw": content}

    # Extract **Key:** Value pairs
    for match in re.finditer(r"\*\*(.+?):\*\*\s*(.+)", content):
        key = match.group(1).strip().lower().replace(" ", "_")
        value = match.group(2).strip()
        soul[key] = value

    # Extract multi-line sections (## Section Header followed by text)
    for match in re.finditer(r"## (.+?)\n(.*?)(?=\n## |\Z)", content, re.DOTALL):
        section_name = match.group(1).strip().lower().replace(" ", "_")
        section_body = match.group(2).strip()
        soul[f"section_{section_name}"] = section_body

    # Friendly aliases for the most-used fields
    soul.setdefault("name", soul.get("name", ""))
    soul.setdefault("bar_enrollment", soul.get("bar_enrollment", ""))

    return soul
