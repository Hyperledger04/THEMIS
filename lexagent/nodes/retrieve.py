# Retrieve node: pull a gold-standard template and past-draft examples before drafting.
# Runs after intake (and after research when applicable) — before the draft node.
# No LLM call, no network call — local files + SQLite FTS only.
# WHY: Grounding the draft node in a known-good structural template eliminates the
# numbered-header and formatting issues that arise from generic system prompts.
# Past-draft BM25 retrieval is a lightweight "memory" that improves with every matter.

import json
import logging
from pathlib import Path

from lexagent.config import LexConfig
from lexagent.state import LexState

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_INDEX_PATH = _TEMPLATES_DIR / "templates_index.json"

# How much total character content to inject per run (avoids bloating the context window)
_MAX_TOTAL_CHARS = 8000


def _load_index() -> dict[str, str]:
    try:
        return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _match_template(matter_type: str, user_input: str, index: dict[str, str]) -> str | None:
    """
    Return the template filename that best matches this matter.
    Checks matter_type first, then scans user_input for S.138-specific signals.
    WHY: The intake node classifies "legal notice" as the matter_type for all notices,
    but S.138 notices need the specialised template. We promote to s138_notice when
    the user brief or statutes mention "138" or "NI Act".
    """
    mt = (matter_type or "").lower().strip()

    # S.138 signal: check user input for NI Act / cheque-specific keywords
    ui = (user_input or "").lower()
    s138_signals = ("138", "ni act", "negotiable instruments", "cheque dishonour", "cheque bounce", "cheque was returned", "dishonoured")
    if any(sig in ui for sig in s138_signals):
        s138_file = index.get("s138_notice") or index.get("cheque dishonour")
        if s138_file:
            return s138_file

    # Direct matter_type key match
    if mt in index:
        return index[mt]

    # Partial match: any index key that is a substring of the matter type
    for key, filename in index.items():
        if key in mt or mt in key:
            return filename

    return None


async def run(state: LexState) -> dict:
    """
    Retrieve gold-standard templates and past-draft examples for the draft node.
    Returns retrieval_chunks: list of {type, content, source} dicts.
    """
    config = LexConfig()
    chunks: list[dict] = []
    total_chars = 0

    matter_type = state.get("matter_type") or ""
    user_input = state.get("user_input") or ""

    # ── Step 1: Template retrieval ────────────────────────────────────────────
    index = _load_index()
    template_file = _match_template(matter_type, user_input, index)

    if template_file:
        template_path = _TEMPLATES_DIR / template_file
        try:
            content = template_path.read_text(encoding="utf-8")
            allowed = _MAX_TOTAL_CHARS - total_chars
            if allowed > 0:
                snippet = content[:allowed]
                chunks.append({"type": "template", "content": snippet, "source": template_file})
                total_chars += len(snippet)
                logger.debug("retrieve: loaded template %s (%d chars)", template_file, len(snippet))
        except Exception as exc:
            logger.warning("retrieve: could not read template %s — %s", template_file, exc)

    # ── Step 2: Past-draft BM25 retrieval ────────────────────────────────────
    # WHY: If the lawyer has drafted similar matters before, those drafts provide
    # concrete stylistic examples that improve consistency across matters.
    if total_chars < _MAX_TOTAL_CHARS and matter_type:
        try:
            from lexagent.memory.session_store import search_sessions

            query = f"{matter_type} {state.get('purpose', '')}".strip()
            past_sessions = search_sessions(query, limit=5, sessions_db=config.sessions_db)

            current_matter_id = state.get("matter_id", "")
            added = 0
            for session in past_sessions:
                if added >= 2:
                    break
                # Skip the current matter and sessions without drafts
                if session.get("matter_id") == current_matter_id:
                    continue
                draft_text = session.get("draft_output") or ""
                if not draft_text or len(draft_text) < 100:
                    continue
                # Only include if same matter type (rough match)
                if session.get("matter_type", "").lower() != matter_type.lower():
                    continue

                allowed = _MAX_TOTAL_CHARS - total_chars
                if allowed <= 0:
                    break

                excerpt = draft_text[:min(1000, allowed)]
                chunks.append({
                    "type": "past_draft",
                    "content": excerpt,
                    "source": session.get("matter_id", "unknown"),
                })
                total_chars += len(excerpt)
                added += 1
                logger.debug("retrieve: added past draft from %s (%d chars)", session.get("matter_id"), len(excerpt))

        except Exception as exc:
            # Past-draft retrieval is best-effort — never block drafting
            logger.warning("retrieve: past-draft retrieval failed — %s", exc)

    return {"retrieval_chunks": chunks}
