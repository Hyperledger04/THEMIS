# Skill Router Node — inserted between intake and draft.
#
# Runs three skill-selection sources and unions them:
#   1. LLM router (gpt-4.1-mini by default) — semantic understanding
#   2. String-match (existing loader logic) — deterministic fallback
#   3. forced_skill_names (CLI --skill flag or Telegram /skill command) — manual override
#
# WHY: Deterministic string matching misses composite matters (e.g. S.138 accused
# also seeking bail). The LLM picks up nuance; string-match ensures obvious cases
# are always covered even if the LLM call fails; forced names let the lawyer override.

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from themis.config import LexConfig
from themis.skills.loader import (
    _string_match_skill_name,
    build_skills_manifest,
    load_skill_stack,
    route_skills,
)
from themis.state import SeniorCounselState

# WHY: Module-level constant so tests can patch it to a tmp_path with fixture skills
# without patching the entire config object.
BUNDLED_SKILLS_DIR = Path(__file__).parent.parent / "skills"

_stderr_console = Console(stderr=True)


async def run(state: SeniorCounselState) -> dict:
    """
    Select and load the best skill stack for this matter.
    Always succeeds — falls back to empty skill (base prompt only) on any failure.
    """
    try:
        cfg = LexConfig()
        user_skills_dir = Path(cfg.skills_dir).expanduser()

        matter_type = state.get("matter_type") or ""
        user_input = state.get("user_input") or ""
        matter_summary = f"{matter_type} — {user_input}"[:500]
        forced: list[str] = list(state.get("forced_skill_names") or [])

        # ── Source 1: LLM router ───────────────────────────────────────────
        manifest = build_skills_manifest(BUNDLED_SKILLS_DIR, user_skills_dir)
        router_result = await route_skills(matter_summary, manifest, cfg)
        llm_selected: list[str] = router_result.get("selected") or []
        unmatched: list[str] = router_result.get("unmatched") or []

        # ── Source 2: string-match ─────────────────────────────────────────
        string_name = _string_match_skill_name(matter_type, BUNDLED_SKILLS_DIR, user_skills_dir)
        string_matched: list[str] = [string_name] if string_name else []

        # ── Union (dedup, preserve order: llm first, then string, then forced) ──
        seen: set[str] = set()
        final_names: list[str] = []
        for name in [*llm_selected, *string_matched, *forced]:
            if name and name not in seen:
                seen.add(name)
                final_names.append(name)

        # ── Load skill bodies ──────────────────────────────────────────────
        active_skill = ""
        if final_names:
            # WHY: load_skill_stack takes matter_type for primary matching and
            # agent_skill_names for secondary. Passing first name as matter_type
            # (exact name match) and the rest as supporting names.
            active_skill = load_skill_stack(
                final_names[0],
                BUNDLED_SKILLS_DIR,
                user_skills_dir,
                agent_skill_names=final_names[1:],
            )

        # ── Gap log + terminal nudge ───────────────────────────────────────
        if unmatched:
            _append_gap_log(matter_summary, unmatched, cfg)
            _show_gap_nudge(unmatched)

        # ── Routing summary line ───────────────────────────────────────────
        if final_names:
            _stderr_console.print(f"[dim]Skill router:[/dim] {', '.join(final_names)}")
        else:
            _stderr_console.print("[dim]Skill router: no skill loaded — using base prompt[/dim]")

        return {
            "active_skill": active_skill or None,
            "active_skill_name": ", ".join(final_names) if final_names else None,
            "selected_skill_names": final_names if final_names else None,
        }

    except Exception as e:
        # WHY: Never block the graph — degrade silently to base prompt.
        _stderr_console.print(f"[dim yellow]Skill router failed ({e}); using base prompt.[/dim yellow]")
        return {}


def _append_gap_log(matter_summary: str, missing: list[str], cfg: LexConfig) -> None:
    """Append one line per gap event to ~/.themis/missing_skills.log."""
    try:
        log_path = Path(cfg.home_dir).expanduser() / "missing_skills.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        safe_summary = matter_summary.replace('"', "'")[:120]
        missing_json = str(missing).replace("'", '"')
        line = f'{ts}  matter="{safe_summary}"  missing={missing_json}\n'
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # gap log failure must never surface to the user


def _show_gap_nudge(missing: list[str]) -> None:
    """Show a Rich Panel nudge to stderr listing unmatched skills."""
    missing_lines = "\n".join(f"    {name}  — not found" for name in missing)
    create_cmd = f"lex skill create {missing[0]}" if missing else "lex skill create <name>"
    panel_text = (
        f"The router identified {len(missing)} skill(s) not yet in your library:\n\n"
        f"{missing_lines}\n\n"
        "Drafting without it. To add this skill later:\n"
        f"  [bold cyan]{create_cmd}[/bold cyan]\n"
        "Or load an existing skill manually:\n"
        "  [bold cyan]lex skill load <name>[/bold cyan]   /   Telegram: [bold cyan]/skill <name>[/bold cyan]"
    )
    _stderr_console.print(
        Panel(panel_text, title="[yellow]Skill Gap Detected[/yellow]", border_style="yellow"),
        file=sys.stderr,
    )
