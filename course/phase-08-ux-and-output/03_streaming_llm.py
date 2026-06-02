"""
Phase 8 — UX & Output: 03_streaming_llm.py
===========================================
Token streaming from an LLM — how LexAgent writes draft text
word-by-word to the terminal instead of waiting for the full response.

No API key required — all demos use a fake token generator.
Run: python 03_streaming_llm.py
"""

import time
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console()


# ── SECTION 1: WHY STREAM? ───────────────────────────────────────────────────

# WRONG — wait for the full LLM response before showing anything.
# A 2,500-word writ petition takes 40–60 seconds. The user sees nothing.
def wrong_no_streaming(prompt: str) -> str:
    # Imagine this is a real LLM call that takes 45 seconds...
    time.sleep(0.1)  # simulated
    return "IN THE HON'BLE HIGH COURT OF DELHI AT NEW DELHI..."

# RIGHT — stream tokens as they arrive. The user sees words appearing
# immediately, just like ChatGPT. This is what LexAgent does via
# the stream_cb parameter in call_llm() (lexagent/nodes/_llm.py:35).


# ── SECTION 2: THE stream_cb PATTERN ─────────────────────────────────────────

# The key insight: call_llm() accepts a callback function.
# Every time the LLM produces a token, call_llm() calls stream_cb(token).
# The caller decides what to DO with each token.

# This is the simplest possible stream_cb:
def on_token(token: str) -> None:
    """
    Called by call_llm() for each token that arrives from the LLM.

    WHY flush=True: Python buffers stdout by default. Without flush=True,
    tokens accumulate in the buffer and appear in chunks rather than one
    by one. flush=True forces the buffer to empty after every token — you
    see each word the instant the LLM generates it.

    WHY end="": print() adds a newline by default. LLM tokens are raw
    subword pieces (not full lines), so we must NOT add newlines.
    """
    print(token, end="", flush=True)  # flush=True is critical


# In LexAgent's CLI (lexagent/cli.py), the stream_cb used is:
#
#   def stream_cb(token: str) -> None:
#       live_status.stream_token(token)
#
# And LiveStatus.stream_token() does:
#   self._console.print(token, end="", markup=False, highlight=False)
#
# markup=False prevents Rich from accidentally interpreting legal text like
# "[Section 138]" as Rich markup tags. highlight=False stops Rich from
# colour-coding numbers and strings in the draft.


# ── SECTION 3: FAKE TOKEN GENERATOR ──────────────────────────────────────────

def fake_llm_stream(prompt: str, delay: float = 0.03):
    """
    Generator that yields fake LLM tokens with a small delay.
    Simulates the real LiteLLM streaming interface without an API key.

    In real LiteLLM (lexagent/nodes/_llm.py:72-77):
        response = await litellm.acompletion(**kwargs, stream=True)
        async for chunk in response:
            token = chunk.choices[0].delta.content or ""
            if token:
                stream_cb(token)
                full_text += token

    This generator simulates that chunk loop synchronously.
    """
    # A 30-token sample of what a writ petition draft looks like
    fake_tokens = [
        "IN ", "THE ", "HON'BLE ", "HIGH ", "COURT ", "OF ", "DELHI ",
        "AT ", "NEW ", "DELHI\n\n",
        "WRIT ", "PETITION ", "(CIVIL) ", "NO. ", "____/2024\n\n",
        "IN ", "THE ", "MATTER ", "OF:\n\n",
        "Ravi ", "Kumar ", "... ", "Petitioner\n",
        "versus\n",
        "Union ", "of ", "India ", "... ", "Respondent\n\n",
        "PETITION ", "UNDER ", "ARTICLE ", "226 ",
    ]
    for token in fake_tokens:
        time.sleep(delay)
        yield token


# ── SECTION 4: CALLING THE STREAM ─────────────────────────────────────────────

def call_llm_simulated(
    messages: list[dict],
    stream_cb: Callable[[str], None] | None = None,
) -> dict:
    """
    Simulated version of lexagent/nodes/_llm.py:call_llm().

    The real signature is:
        async def call_llm(messages, cfg, *, tools, stream_cb, system, model_override) -> dict

    When stream_cb is provided:
    1. LiteLLM opens a streaming connection to the LLM
    2. For each arriving chunk, it extracts the token and calls stream_cb(token)
    3. It accumulates the full text locally
    4. It returns {"content": full_text, "tool_calls": None} when done

    The CALLER never waits for the full text — it sees tokens arriving via callback.
    """
    prompt = messages[-1]["content"] if messages else ""

    full_text = ""
    for token in fake_llm_stream(prompt, delay=0.03):
        if stream_cb:
            stream_cb(token)
        full_text += token

    return {"content": full_text, "tool_calls": None}


def demo_basic_streaming():
    console.rule("[bold]SECTION 4 — Basic Streaming Demo[/bold]")
    console.print("[dim]Watch tokens appear word by word...[/dim]")
    console.print()

    messages = [
        {"role": "system", "content": "You are a senior Indian advocate."},
        {"role": "user",   "content": "Draft the opening of a writ petition."},
    ]

    result = call_llm_simulated(messages, stream_cb=on_token)

    # After all tokens arrive, print a newline and the token count
    print()   # on_token used end="" so we need a final newline
    console.print()
    console.print(
        f"[dim]Total characters received: {len(result['content'])}[/dim]"
    )
    console.print()


# ── SECTION 5: TWO CACHE LAYERS ───────────────────────────────────────────────

def demo_cache_layers():
    console.rule("[bold]SECTION 5 — Two-Layer Caching Architecture[/bold]")

    # From lexagent/nodes/_llm.py module docstring:
    #
    # LAYER 1 — LiteLLM disk cache (all providers)
    # ─────────────────────────────────────────────
    # litellm.Cache caches exact prompt+response pairs on disk.
    # If you run the SAME prompt twice (e.g., re-running a test), the
    # second call returns instantly with no API cost.
    #
    # Setup (from lexagent/nodes/_llm.py:88-105):
    #   litellm.cache = litellm.Cache(type="disk", disk_cache_dir="~/.lexagent/llm_cache")
    #
    # Result: tests that hit the same prompt are blazing fast after the first run.

    console.print(
        Panel(
            "[bold cyan]Layer 1 — LiteLLM Disk Cache[/bold cyan]\n\n"
            "  [green]✓[/green] Works with ALL providers (Anthropic, OpenAI, Gemini)\n"
            "  [green]✓[/green] Caches by exact prompt hash → disk file\n"
            "  [green]✓[/green] Survives process restarts (across CLI runs)\n"
            "  [green]✓[/green] Enabled via: litellm.Cache(type='disk')\n"
            "  [dim]Config: LexConfig.enable_prompt_caching → cfg.caching kwarg[/dim]",
            border_style="cyan",
        )
    )

    console.print()

    # LAYER 2 — Anthropic server-side prompt caching
    # ─────────────────────────────────────────────────────────────────────
    # When using Anthropic models, the SYSTEM PROMPT can be cached on
    # Anthropic's servers. Even when the USER MESSAGE changes (new matter),
    # the system prompt tokens are served from cache at ~10% of normal cost.
    #
    # CRITICAL RULE from lexagent/nodes/_llm.py:
    # "Matter memory NEVER goes in the system prompt. Memory always goes
    # in the user turn so the system prompt stays cacheable."
    #
    # Without this rule: every new matter changes the system prompt →
    # cache miss every time → 10× more expensive.

    console.print(
        Panel(
            "[bold yellow]Layer 2 — Anthropic Server-Side Prompt Caching[/bold yellow]\n\n"
            "  [green]✓[/green] Anthropic only — uses cache_control in message blocks\n"
            "  [green]✓[/green] System prompt cached even when user message changes\n"
            "  [green]✓[/green] ~90% cost saving on system prompt tokens\n"
            "  [red]✗[/red] SOUL.md and matter memory must be in the USER turn\n"
            "  [dim]Why: system prompt must be identical across calls to hit cache[/dim]",
            border_style="yellow",
        )
    )
    console.print()


# ── SECTION 6: WHAT STREAMING LOOKS LIKE ────────────────────────────────────

def demo_streaming_visual():
    """
    Show a slower stream so the student can clearly see each token arriving.
    Uses a different callback that adds Rich colour to the draft text.
    """
    console.rule("[bold]SECTION 6 — Streaming at Human-Readable Speed[/bold]")
    console.print(
        "[dim]Same stream as Section 4, but at 120ms per token "
        "so you can see each piece arrive...[/dim]"
    )
    console.print()

    # A coloured callback — highlights legal terms as they stream in
    LEGAL_TERMS = {"HON'BLE", "WRIT", "PETITION", "ARTICLE", "VERSUS"}
    buffer = []

    def coloured_on_token(token: str) -> None:
        stripped = token.strip().upper()
        if stripped in LEGAL_TERMS:
            # Bold + cyan for recognised legal terms
            console.print(f"[bold cyan]{token}[/bold cyan]", end="", markup=True)
        else:
            console.print(token, end="", markup=False, highlight=False)
        buffer.append(token)

    messages = [{"role": "user", "content": "Draft writ petition opening."}]

    for token in fake_llm_stream(messages[-1]["content"], delay=0.12):
        coloured_on_token(token)

    print()
    console.print()
    console.print(
        "[dim]In production: markup=False, highlight=False to avoid mangling "
        "legal text like '[Section 138]'[/dim]"
    )
    console.print()


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.print()
    console.print(
        Panel(
            "[bold]Phase 8 — UX & Output[/bold]\n"
            "[dim]Token streaming and LLM caching patterns[/dim]",
            border_style="blue",
        )
    )
    console.print()

    demo_basic_streaming()
    demo_cache_layers()
    demo_streaming_visual()


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/nodes/_llm.py, lines 69-78. The streaming loop is:
#       async for chunk in response:
#           token = chunk.choices[0].delta.content or ""
#    Why is `or ""` needed? What does the LiteLLM chunk contain when the
#    model is "thinking" (producing no visible token)?
#
# 2. In lexagent/nodes/_llm.py, stream_cb is typed as Callable[[str], None].
#    The CLI's actual callback is live_status.stream_token(token).
#    Why is the callback injected at call time rather than hardcoded inside
#    call_llm()? Name one test in tests/ that benefits from this design.
#
# 3. The module docstring of lexagent/nodes/_llm.py says:
#    "Matter memory NEVER goes in the system prompt."
#    If a developer added matter memory to the system prompt to simplify
#    the message-building code, what would happen to the Anthropic cache?
#    How much would it cost per matter (in relative terms)?
#
# 4. Why does lexagent/ui/live.py:95 use markup=False when printing
#    stream tokens? Give a concrete example of Indian legal text that
#    would break without that flag.
#
# 5. The LiteLLM disk cache is set up in lexagent/nodes/_llm.py:setup_litellm_cache().
#    It stores cache in ~/.lexagent/llm_cache. What happens to the cache
#    when a lawyer changes their SOUL.md drafting preferences? Should the
#    cache be invalidated? How would you implement that?
