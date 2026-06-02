"""
Phase 8 — UX & Output: 05_loading_messages.py
===============================================
YAML-driven loading messages for the LexAgent pipeline.
Teach how loading_messages.yaml and legal_trivia.yaml power
the animated CLI and Telegram spinner experience.

Install: pip install pyyaml rich
Run:     python 05_loading_messages.py
"""

import random
import time

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console()


# ── SECTION 1: WHY YAML FOR MESSAGES? ────────────────────────────────────────

# WRONG — hard-code spinner messages inside Python node files.
# The lawyer using LexAgent can't customise them without editing source code.
# Adding a new message means a code change, PR, and deploy cycle.
def wrong_hardcoded():
    node_name = "research"
    if node_name == "research":
        msg = "Researching..."  # buried in Python, untouchable by the lawyer
    elif node_name == "draft":
        msg = "Drafting..."
    return msg

# RIGHT — messages live in a YAML file the lawyer CAN edit.
# lexagent/data/loading_messages.yaml maps node_name → list of messages.
# The loader picks one randomly at runtime — variety without code changes.


# ── SECTION 2: YAML BASICS ───────────────────────────────────────────────────

def demo_yaml_basics():
    console.rule("[bold]SECTION 2 — YAML Basics[/bold]")

    # yaml.safe_load() parses a YAML string into a Python dict/list.
    # safe_load (not load) prevents arbitrary Python object construction — safer.
    simple_yaml = """
intake:
  - Analysing your brief...
  - Reading your matter brief...
  - Identifying matter type and parties...
research:
  - Searching Indian Kanoon...
  - Reading 47 judgments so you don't have to...
"""
    data = yaml.safe_load(simple_yaml)

    console.print("[bold]Parsed YAML structure:[/bold]")
    for node_name, messages in data.items():
        console.print(f"  [cyan]{node_name}[/cyan]: {len(messages)} message(s)")
        for msg in messages:
            console.print(f"    [dim]- {msg}[/dim]")

    console.print()
    # random.choice() picks one at random — different message every run
    chosen = random.choice(data["research"])
    console.print(f"[bold]random.choice for 'research':[/bold] [green]{chosen}[/green]")
    console.print()


# ── SECTION 3: THE FULL MESSAGES STRUCTURE ───────────────────────────────────

# This mirrors lexagent/data/loading_messages.yaml exactly.
# (Inlined so this file runs standalone without needing the LexAgent package.)
LOADING_MESSAGES_YAML = """
# Contextual progress messages shown during graph execution.
# {placeholders} can be filled from state fields at runtime.

intake:
  - "Analysing your brief..."
  - "Reading your matter brief..."
  - "Identifying matter type and parties..."
  - "Lexatating..."
  - "Raising objections internally..."

research:
  - "Searching Indian Kanoon for precedents..."
  - "Pulling Supreme Court and High Court judgments..."
  - "Reading judgments and extracting relevant citations..."
  - "Running limitation analysis and statute check..."
  - "Negotiating with Indian Kanoon..."
  - "Reading 47 judgments so you don't have to..."
  - "Arguing with databases..."
  - "Debating precedent..."

draft:
  - "Drafting your writ petition..."
  - "Writing with verified citations..."
  - "Drafting with extreme prejudice..."
  - "Objecting to bad sentence structure..."
  - "Lawyering..."
  - "Hereinafter referred to as 'almost done'..."

cite:
  - "Verifying citations against Indian Kanoon corpus..."
  - "Cross-referencing citations — checking every case number..."
  - "Grounding each citation to a source chunk..."
  - "Cross-examining citations..."
  - "Holding citations in contempt..."

review:
  - "Final review — checking length, citations, and structure..."
  - "Quality check in progress..."
  - "Your Honour, the draft is ready..."
  - "The ayes have it..."
"""

LEGAL_TRIVIA_YAML = """
trivia:
  - fact: "Article 32 is the 'heart and soul' of the Constitution — Dr. B.R. Ambedkar's own words."
    category: "Constitution"
  - fact: "The CPC, 1908 has survived two world wars, three constitutions, and infinite adjournments."
    category: "CPC"
  - fact: "India has over 50 million pending court cases. Your adjournment is statistically normal."
    category: "Judiciary"
  - fact: "Nani Palkhivala argued Kesavananda Bharati for 31 days straight. The judgment: 703 pages."
    category: "Legends"
  - fact: "Order XXXIX Rule 1 & 2 CPC governs temporary injunctions — the most invoked Order in civil litigation."
    category: "CPC"
  - fact: "Section 138 NI Act (cheque bounce) accounts for ~40% of all criminal cases in India."
    category: "NI Act"
  - fact: "PIL was pioneered in India by Justice P.N. Bhagwati and Justice V.R. Krishna Iyer in the late 1970s."
    category: "PIL"
  - fact: "Calcutta High Court is India's oldest, established in 1862. Allahabad is the largest by judge strength."
    category: "High Courts"
"""


def demo_full_structure():
    console.rule("[bold]SECTION 3 — Full Messages Structure[/bold]")

    messages = yaml.safe_load(LOADING_MESSAGES_YAML)
    trivia_data = yaml.safe_load(LEGAL_TRIVIA_YAML)

    # Show node count and message variety
    console.print(f"[bold]Nodes in loading_messages.yaml:[/bold]")
    for node, msgs in messages.items():
        console.print(f"  [cyan]{node:<12}[/cyan] {len(msgs)} messages")

    console.print()
    console.print(f"[bold]Legal trivia entries:[/bold] {len(trivia_data['trivia'])}")
    console.print()


# ── SECTION 4: get_message() WITH FALLBACK ────────────────────────────────────

def get_message(node_name: str, messages: dict) -> str:
    """
    Get a random loading message for the given node name.

    Args:
        node_name: The graph node key (e.g. "research", "draft")
        messages:  The parsed YAML dict from loading_messages.yaml

    Returns:
        A randomly selected message string, or "Working..." if the node
        has no entry. The fallback prevents a KeyError when a new node
        is added to the graph before its messages are added to the YAML.

    WHY random.choice over index 0: variety. A lawyer running LexAgent
    daily notices if the same phrase appears every time — randomness makes
    the tool feel alive rather than mechanical.
    """
    node_messages = messages.get(node_name)
    if not node_messages:
        return "Working..."
    return random.choice(node_messages)


def demo_get_message():
    console.rule("[bold]SECTION 4 — get_message() with Fallback[/bold]")

    messages = yaml.safe_load(LOADING_MESSAGES_YAML)

    # Known node — picks from the list
    for _ in range(3):
        msg = get_message("research", messages)
        console.print(f"  research → [green]{msg}[/green]")

    console.print()

    # Unknown node — fallback to "Working..."
    msg = get_message("rag_retrieval", messages)   # not in YAML yet
    console.print(f"  rag_retrieval (unknown) → [yellow]{msg}[/yellow]  (fallback)")
    console.print()


# ── SECTION 5: LEGAL TRIVIA DURING LONG WAITS ────────────────────────────────

def get_trivia(trivia_data: dict) -> str:
    """
    Return a random legal trivia fact for display during long waits.

    LexAgent shows trivia in the setup wizard (lex setup) and during
    unusually long research calls. Legal trivia keeps the lawyer engaged
    and makes waiting feel educational rather than frustrating.
    """
    facts = trivia_data.get("trivia", [])
    if not facts:
        return "India has one of the world's largest court systems."
    entry = random.choice(facts)
    category = entry.get("category", "Legal")
    fact = entry.get("fact", "")
    return f"[{category}] {fact}"


def demo_trivia():
    console.rule("[bold]SECTION 5 — Legal Trivia[/bold]")

    trivia_data = yaml.safe_load(LEGAL_TRIVIA_YAML)

    console.print("[dim]Showing 3 random trivia facts (as seen during 'lex setup'):[/dim]")
    console.print()

    for i in range(3):
        fact = get_trivia(trivia_data)
        console.print(
            Panel(
                f"[italic]{fact}[/italic]",
                title=f"[dim]Did you know? ({i+1}/3)[/dim]",
                border_style="dim",
                padding=(0, 2),
            )
        )
        time.sleep(0.3)

    console.print()


# ── SECTION 6: PIPELINE SIMULATION WITH MESSAGES ─────────────────────────────

def demo_pipeline():
    """
    Simulate a 5-node pipeline cycling through loading messages.
    This mirrors what lexagent/ui/live.py does during a real draft run,
    using the YAML-driven messages for each node transition.
    """
    console.rule("[bold]SECTION 6 — 5-Node Pipeline Simulation[/bold]")

    messages = yaml.safe_load(LOADING_MESSAGES_YAML)
    trivia_data = yaml.safe_load(LEGAL_TRIVIA_YAML)

    pipeline = [
        ("intake",    0.4),
        ("research",  0.8),   # longer — show 2 messages
        ("draft",     0.8),   # longer — show 2 messages
        ("cite",      0.4),
        ("review",    0.4),
    ]

    console.print("[dim]Simulating pipeline (no real LLM calls)...[/dim]")
    console.print()

    for node_name, delay in pipeline:
        msg = get_message(node_name, messages)
        console.print(f"  [cyan]→[/cyan] [bold]{node_name:<12}[/bold] {msg}")
        time.sleep(delay)

        # For long nodes, show a second message
        if delay > 0.5:
            msg2 = get_message(node_name, messages)
            console.print(f"  [cyan]→[/cyan] [bold]{node_name:<12}[/bold] {msg2}")
            time.sleep(delay)

        console.print(f"  [green]✓[/green] [bold]{node_name:<12}[/bold] complete")

    console.print()

    # Show a trivia fact at the end (as during setup wizard)
    trivia = get_trivia(trivia_data)
    console.print(
        Panel(
            f"[italic cyan]{trivia}[/italic cyan]",
            title="[dim]While your draft is saved...[/dim]",
            border_style="dim",
        )
    )
    console.print()


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.print()
    console.print(
        Panel(
            "[bold]Phase 8 — UX & Output[/bold]\n"
            "[dim]YAML-driven loading messages and legal trivia[/dim]",
            border_style="blue",
        )
    )
    console.print()

    demo_yaml_basics()
    demo_full_structure()
    demo_get_message()
    demo_trivia()
    demo_pipeline()


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/data/loading_messages.yaml. Some messages have
#    {placeholders} like "Searching Indian Kanoon for {matter_type}...".
#    The loader in this file doesn't fill them — write the one-liner that
#    would. Where in LexAgent would you call it? (Hint: the node that
#    calls get_message() has access to LexState.)
#
# 2. lexagent/data/legal_trivia.yaml has a `category` field on each fact.
#    If you wanted to show only "CPC" trivia during draft runs (not setup),
#    how would you filter the trivia list before calling random.choice()?
#    Write the two-line list comprehension.
#
# 3. The YAML for loading_messages.yaml uses quoted strings ("...") for
#    messages with apostrophes like "Hereinafter referred to as 'almost done'".
#    What happens in YAML if you use an unquoted string containing a colon?
#    Try removing a quote pair and calling yaml.safe_load() — what error do you get?
#
# 4. The get_message() fallback returns "Working..." for unknown nodes.
#    If you added a new graph node called "rag_retrieval" to LexAgent,
#    name the exact file and YAML key you would add. Would you need to
#    change any Python files to make the message appear?
#
# 5. LexAgent loads loading_messages.yaml using importlib.resources so it
#    works whether the package is installed via `pip install lexagent` or
#    run from source. What would break if you used open("loading_messages.yaml")
#    with a relative path instead? Which two deployment scenarios would fail?
