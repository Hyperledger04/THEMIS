# Telegram gateway for Themis — Phase 8 UX overhaul.
#
# Key improvements over Phase 7:
#   - Inline keyboard buttons for binary/MCQ intake questions (one question per message)
#   - Session persistence: in-progress matters survive bot restarts via SQLite
#   - /resume command: lists recent matters with inline [Resume] buttons
#   - Agentic tool routing: user selects which research sources to use before research runs
#   - .docx auto-delivery: every completed draft sent as a file attachment
#   - Post-draft action menu: email, Drive, eCourts lookup, redraft, forward, DocuSign
#   - Contextual progress messages from loading_messages.yaml
#   - Skill visibility: shows which skill was loaded
#   - /setup command: in-Telegram wizard for lawyer profile + API keys + MCP toggles

import asyncio
import logging
import os
import random
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console
from telegram import (
    Document,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from themis.config import LexConfig
from themis.graph import get_graph, setup_checkpointer
from themis.state import LexState

console = Console()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Loading messages
# ---------------------------------------------------------------------------

def _load_messages() -> dict:
    path = Path(__file__).parent.parent / "data" / "loading_messages.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


_LOADING_MSGS: dict = {}


def _progress_text(node_name: str, state: dict) -> str:
    global _LOADING_MSGS
    if not _LOADING_MSGS:
        _LOADING_MSGS = _load_messages()

    pool = _LOADING_MSGS.get(node_name, [])
    if not pool:
        fallbacks = {
            "intake": "📋 Intake…",
            "research": "🔍 Researching…",
            "draft": "✍️ Drafting…",
            "cite": "📌 Verifying citations…",
            "review": "✅ Review…",
            "contract_review": "📄 Reviewing contract…",
        }
        return fallbacks.get(node_name, f"⚖️ {node_name}…")

    template = random.choice(pool)
    # Fill placeholders from state
    matter_type = state.get("matter_type") or "document"
    jurisdiction = state.get("jurisdiction") or "court"
    purpose = (state.get("purpose") or "")[:60]
    grounded = state.get("grounded_citations") or []
    n_citations = str(len(grounded))

    return (
        template
        .replace("{matter_type}", matter_type)
        .replace("{jurisdiction}", jurisdiction)
        .replace("{purpose}", purpose)
        .replace("{n_citations}", n_citations)
    )


# ---------------------------------------------------------------------------
# Session dataclass
# ---------------------------------------------------------------------------

@dataclass
class TelegramSession:
    """Per-user session state mapping Telegram user_id → Themis matter context."""
    matter_id: str
    graph_state: Optional[dict] = None
    completed: bool = False
    # Queue of structured question objects waiting to be sent one-by-one
    pending_questions: list = field(default_factory=list)
    # If set, the next free-text message answers this field name
    awaiting_free_text_for: Optional[str] = None
    # Post-draft: what action is pending input for (e.g. "email_recipient")
    awaiting_post_draft_input: Optional[str] = None
    # Setup wizard state (see setup_wizard.py)
    setup_step: int = 0
    setup_data: dict = field(default_factory=dict)
    in_setup: bool = False
    # Tool routing: True once user has selected tools for current matter
    tools_approved: bool = False


_sessions: dict[int, TelegramSession] = {}

# Pattern matching internal Themis matter IDs (e.g. M-FC4A838E)
_MATTER_ID_RE = re.compile(r'\bM-[A-F0-9]{8}\b')


def _get_or_create_session(user_id: int, cfg: LexConfig) -> TelegramSession:
    if user_id in _sessions:
        return _sessions[user_id]

    # Phase 9: When Postgres checkpointer is active, the full matter state lives
    # in LangGraph's checkpoint tables — we no longer need to manually reload it
    # from session_store.py. We just need to know the last matter_id for this user
    # so we can pass the right thread_id to graph.astream().
    #
    # Fall back to session_store only when Postgres isn't configured (stub mode).
    if not cfg.postgres_url:
        try:
            from themis.memory.session_store import list_sessions, get_session_state
            recent = list_sessions(limit=5, sessions_db=cfg.sessions_db)
            for row in recent:
                state_json = get_session_state(row["matter_id"], sessions_db=cfg.sessions_db)
                if state_json and state_json.get("telegram_user_id") == user_id:
                    session = TelegramSession(
                        matter_id=row["matter_id"],
                        graph_state=state_json,
                        completed=bool(state_json.get("draft_output")),
                    )
                    _sessions[user_id] = session
                    return session
        except Exception:
            pass

    session = TelegramSession(matter_id=f"M-{uuid.uuid4().hex[:8].upper()}")
    _sessions[user_id] = session
    return session


def _graph_config(matter_id: str, user_id: int, cfg: LexConfig) -> dict:
    """
    Build the LangGraph invocation config for a given matter.

    LANGGRAPH: thread_id is the key that identifies a LangGraph checkpoint
    thread. Every graph.astream(state, config=_graph_config(...)) call with
    the same thread_id resumes from the last saved checkpoint automatically.
    This replaces the entire manual _persist_session() / _get_or_create_session()
    SQLite dance from Phase 8.

    WHY user_id in configurable: LangGraph passes configurable values through
    to nodes via RunnableConfig. Nodes can read user_id for per-lawyer soul
    loading and per-firm Qdrant collection routing.
    """
    return {
        "configurable": {
            "thread_id": matter_id,
            "user_id": str(user_id),
            "firm_id": cfg.default_firm_id,
        }
    }


def _is_allowed(user_id: int, cfg: LexConfig) -> bool:
    if not cfg.telegram_allowed_users:
        return True
    return user_id in cfg.telegram_allowed_users


def _escape_md(text: str) -> str:
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)


async def _send_long(message: Message, text: str) -> None:
    limit = 4000
    for i in range(0, len(text), limit):
        chunk = text[i: i + limit]
        try:
            await message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await message.reply_text(chunk)


# ---------------------------------------------------------------------------
# Inline keyboard helpers
# ---------------------------------------------------------------------------

def _make_binary_keyboard(field: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes ✓", callback_data=f"ans:{field}:yes"),
        InlineKeyboardButton("No ✗", callback_data=f"ans:{field}:no"),
    ]])


def _make_mcq_keyboard(field: str, options: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(options[:4]):
        rows.append([InlineKeyboardButton(opt, callback_data=f"ans:{field}:{i}")])
    rows.append([InlineKeyboardButton("✏️ Other — type below", callback_data=f"ans:{field}:other")])
    return InlineKeyboardMarkup(rows)


async def _send_next_question(
    message: Message,
    session: TelegramSession,
) -> bool:
    """
    Pop and send the next pending question with appropriate inline keyboard.
    Returns True if a question was sent, False if the queue is empty.
    """
    if not session.pending_questions:
        return False

    q = session.pending_questions.pop(0)
    field = q.get("field", "answer")
    question_text = q.get("question", "")
    qtype = q.get("type", "open")
    options = q.get("options", [])

    if qtype == "binary":
        await message.reply_text(
            f"❓ {question_text}",
            reply_markup=_make_binary_keyboard(field),
        )
    elif qtype == "mcq" and options:
        await message.reply_text(
            f"❓ {question_text}",
            reply_markup=_make_mcq_keyboard(field, options),
        )
    else:
        # Open question — just send text, await next message
        await message.reply_text(f"❓ {question_text}")
        session.awaiting_free_text_for = field

    return True


def _make_tool_routing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Indian Kanoon", callback_data="tool:kanoon"),
            InlineKeyboardButton("🌐 Web search", callback_data="tool:web"),
        ],
        [
            InlineKeyboardButton("⚖️ eCourts case status", callback_data="tool:ecourts"),
            InlineKeyboardButton("⏭ Skip research", callback_data="tool:skip"),
        ],
    ])


def _make_post_draft_keyboard(matter_type: str) -> InlineKeyboardMarkup:
    is_contract = "contract" in matter_type.lower()
    rows = [
        [
            InlineKeyboardButton("📧 Send by email", callback_data="action:email"),
            InlineKeyboardButton("💾 Upload to Drive", callback_data="action:drive"),
        ],
        [
            InlineKeyboardButton("🔍 eCourts lookup", callback_data="action:ecourts"),
            InlineKeyboardButton("↩ Redraft", callback_data="action:redraft"),
        ],
        [
            InlineKeyboardButton("👤 Forward for review", callback_data="action:forward"),
        ],
    ]
    if is_contract:
        rows.append([InlineKeyboardButton("🔏 DocuSign", callback_data="action:docusign")])
    rows.append([InlineKeyboardButton("✅ Done", callback_data="action:done")])
    return InlineKeyboardMarkup(rows)


def _make_resume_keyboard(matters: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for m in matters[:5]:
        label = f"{m['matter_id']}: {m.get('matter_type') or 'Matter'}"
        if m.get("jurisdiction"):
            label += f" – {m['jurisdiction'][:20]}"
        rows.append([InlineKeyboardButton(label, callback_data=f"resume:{m['matter_id']}")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Matter ID auto-loader
# ---------------------------------------------------------------------------

async def _try_load_matter(
    user_id: int,
    text: str,
    session: TelegramSession,
    cfg: LexConfig,
    message: Message,
) -> bool:
    """
    If `text` references an existing matter ID, load it into the session.
    Returns True if a matter was loaded. The session in _sessions is updated in-place.

    WHY: Lawyers routinely refer to an earlier matter by ID. Without this check
    the bot starts fresh intake every time, re-asking questions the lawyer already
    answered in a previous session or via the CLI.
    """
    # Search in upper-cased text so "m-fc4a838e" also matches
    match = _MATTER_ID_RE.search(text.upper())
    if not match:
        return False

    matter_id = match.group(0)
    # Already loaded — don't reload
    if session.matter_id == matter_id and session.graph_state:
        return False

    try:
        from themis.memory.session_store import get_session_state
        state = get_session_state(matter_id, sessions_db=cfg.sessions_db)
        if state:
            session.matter_id = matter_id
            session.graph_state = state
            session.completed = bool(state.get("draft_output"))
            session.pending_questions = []
            session.awaiting_free_text_for = None
            _sessions[user_id] = session

            mt = state.get("matter_type") or "Unknown"
            jur = state.get("jurisdiction") or "?"
            await message.reply_text(
                f"📂 *Loaded matter `{matter_id}`*\nType: {mt} | Court: {jur}",
                parse_mode=ParseMode.MARKDOWN,
            )
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Graph runner
# ---------------------------------------------------------------------------

async def _run_graph_for_user(
    user_id: int,
    message: Message,
    cfg: LexConfig,
    initial_brief: str,
    workflow_mode: str = "draft",
    contract_upload_path: Optional[str] = None,
) -> None:
    """
    Run the LangGraph for a user and stream progress to Telegram.

    Phase 9 changes:
    - graph.astream() now receives a LangGraph config with thread_id = matter_id.
      The checkpointer (Postgres or MemorySaver) automatically reloads the last
      saved state for this thread — no more manual _persist_session() calls.
    - State is still passed for the initial turn (new matters) or to add the new
      user message. For resumed matters, LangGraph merges the passed state with
      the checkpoint using the add_messages reducer.
    """
    session = _get_or_create_session(user_id, cfg)
    graph = get_graph(cfg)

    # Build the new input for this turn.
    # WHY: We always pass a minimal state dict with the new user message.
    # For a resumed matter, LangGraph's checkpointer merges this with the saved
    # checkpoint — existing fields (matter_type, parties, etc.) are preserved
    # without re-asking. For a new matter, this is the full initial state.
    if session.graph_state and not session.completed:
        # Continuing an existing matter: supply only the delta — the new message
        # and any fields we want to override. Checkpointer fills the rest.
        _core = ["matter_type", "parties", "jurisdiction", "purpose"]
        _prior_complete = bool(session.graph_state.get("intake_complete")) and all(
            bool(session.graph_state.get(f)) for f in _core
        )
        state: LexState = {  # type: ignore[assignment]
            "user_input": initial_brief,
            "matter_id": session.matter_id,
            "messages": [{"role": "user", "content": initial_brief}],
            "intake_complete": _prior_complete,
            "draft_output": None,
            "plain_english_summary": None,
            "telegram_user_id": user_id,
            "firm_id": cfg.default_firm_id,
            "user_id": str(user_id),
        }
    else:
        state = {  # type: ignore[assignment]
            "user_input": initial_brief,
            "matter_id": session.matter_id,
            "intake_complete": False,
            "citations_verified": False,
            "messages": [{"role": "user", "content": initial_brief}],
            "workflow_mode": workflow_mode,
            "contract_upload_path": contract_upload_path,
            "telegram_user_id": user_id,
            "firm_id": cfg.default_firm_id,
            "user_id": str(user_id),
            "approved_tools": (session.graph_state or {}).get("approved_tools"),
        }

    # Set docx_path so review node will write the file
    tmp_docx = f"/tmp/lex_{session.matter_id}.docx"
    state["docx_path"] = tmp_docx  # type: ignore[typeddict-unknown-key]

    # LangGraph config: thread_id routes to the right checkpoint
    langgraph_cfg = _graph_config(session.matter_id, user_id, cfg)

    progress_msg = await message.reply_text("⚖️ Themis is working…")

    try:
        async for event in graph.astream(state, config=langgraph_cfg):
            for node_name, node_state in event.items():
                if not isinstance(node_state, dict):
                    continue

                # Update session state
                if session.graph_state is None:
                    session.graph_state = {}
                session.graph_state.update(node_state)

                # Phase 9: state is persisted automatically by LangGraph checkpointer
                # after every node — no manual _persist_session() needed here.

                # Show contextual progress
                try:
                    await progress_msg.edit_text(_progress_text(node_name, session.graph_state))
                except Exception:
                    pass

                # Phase 8: eCourts nudge — Kanoon returned nothing
                if node_state.get("ecourts_nudge"):
                    await message.reply_text(
                        "⚠️ Indian Kanoon returned no results for this query.\n\n"
                        "Enable the eCourts MCP for better coverage: run /setup → *Enable MCP tools → eCourts MCP*.",
                        parse_mode=ParseMode.MARKDOWN,
                    )

                # Surface skill loading
                if node_state.get("active_skill_name"):
                    skill_name = node_state["active_skill_name"]
                    msgs = _LOADING_MSGS.get("skill_loaded", [])
                    skill_msg = (random.choice(msgs) if msgs else "📚 Skill loaded: {skill_name}").replace("{skill_name}", skill_name)
                    try:
                        await message.reply_text(skill_msg)
                    except Exception:
                        pass

                # Surface intake questions as inline keyboard
                pending_qs = node_state.get("pending_questions")
                if pending_qs and not node_state.get("intake_complete"):
                    try:
                        await progress_msg.delete()
                    except Exception:
                        pass
                    session.pending_questions = list(pending_qs)
                    await _send_next_question(message, session)

                    return  # wait for user reply — LangGraph checkpoint already saved

                # Surface errors
                if node_state.get("error"):
                    await progress_msg.edit_text(f"❌ Error: {node_state['error']}")
                    return

        # --- Graph completed ---
        final_state = session.graph_state or {}
        draft = final_state.get("draft_output") or final_state.get("contract_review_output") or ""

        try:
            await progress_msg.delete()
        except Exception:
            pass

        if not draft:
            await message.reply_text("⚠️ No draft was produced. Please try again with more detail.")
            return

        matter_type = final_state.get("matter_type") or "document"
        await message.reply_text(f"✅ *Matter `{session.matter_id}` complete*", parse_mode=ParseMode.MARKDOWN)

        # Send .docx file if written
        if os.path.exists(tmp_docx):
            safe_name = re.sub(r"[^\w\-]", "_", matter_type)
            fname = f"{safe_name}_{session.matter_id}.docx"
            with open(tmp_docx, "rb") as f:
                await message.reply_document(document=f, filename=fname, caption="📄 Your court-ready document")
            try:
                os.unlink(tmp_docx)
            except OSError:
                pass
        else:
            # Fallback: send text preview
            preview = draft[:800] + ("\n\n…[truncated]" if len(draft) > 800 else "")
            await _send_long(message, preview)

        # Plain English summary
        summary = final_state.get("plain_english_summary")
        if summary:
            await message.reply_text(f"📋 *Summary for client:*\n{summary}", parse_mode=ParseMode.MARKDOWN)

        # Unverified citations warning
        unverified = final_state.get("unverified_citations")
        if unverified:
            await message.reply_text(
                f"⚠️ {len(unverified)} citation(s) could not be verified:\n"
                + "\n".join(f"• {c}" for c in unverified)
            )

        session.completed = True

        # Post-draft action menu
        await message.reply_text(
            "What would you like to do next?",
            reply_markup=_make_post_draft_keyboard(matter_type),
        )

    except Exception as e:
        logger.exception("Graph execution failed for user %d", user_id)
        try:
            await progress_msg.edit_text(f"❌ An error occurred: {e}")
        except Exception:
            await message.reply_text(f"❌ An error occurred: {e}")


def _persist_session(session: TelegramSession, cfg: LexConfig) -> None:
    """
    Sync matter metadata to SQLite FTS index for /matters search.

    Phase 9: Full state persistence is handled by LangGraph's checkpointer.
    This function only keeps the FTS search index (matter_type, parties,
    jurisdiction) in sync so /matters [query] still works when Postgres
    checkpointing is active.
    """
    if not session.graph_state or cfg.postgres_url:
        # Skip when Postgres is active — LangGraph checkpoint IS the source of truth.
        return
    try:
        from themis.memory.session_store import update_session
        update_session(session.graph_state, sessions_db=cfg.sessions_db)  # type: ignore[arg-type]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tool routing
# ---------------------------------------------------------------------------

async def _send_tool_routing(message: Message) -> None:
    await message.reply_text(
        "🔍 *Ready to research. Which sources should I check?*",
        reply_markup=_make_tool_routing_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    session = _get_or_create_session(user.id, cfg)
    await update.message.reply_text(
        f"⚖️ *Welcome to Themis*\n\n"
        f"Matter ID: `{session.matter_id}`\n\n"
        f"Send me your matter brief and I'll draft a court-ready document with verified Indian citations.\n\n"
        f"*Commands:*\n"
        f"/new — start a new matter\n"
        f"/resume — continue a previous matter\n"
        f"/status — show current matter details\n"
        f"/setup — configure your lawyer profile & API keys\n"
        f"/help — show all commands",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    new_id = f"M-{uuid.uuid4().hex[:8].upper()}"
    _sessions[user.id] = TelegramSession(matter_id=new_id)
    await update.message.reply_text(
        f"✨ Started new matter: `{new_id}`\n\nSend your matter brief to begin.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    session = _get_or_create_session(user.id, cfg)
    state = session.graph_state or {}
    lines = [
        f"📋 *Matter ID:* `{session.matter_id}`",
        f"*Status:* {'✅ Complete' if session.completed else '🔄 In progress'}",
    ]
    if state.get("matter_type"):
        lines.append(f"*Type:* {state['matter_type']}")
    if state.get("jurisdiction"):
        lines.append(f"*Jurisdiction:* {state['jurisdiction']}")
    if state.get("active_skill_name"):
        lines.append(f"*Skill:* {state['active_skill_name']}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    args = context.args or []
    if args:
        # /resume M-XXXXXX — load directly
        matter_id = args[0].upper()
        await _resume_matter(update.message, user.id, matter_id, cfg)
        return

    # Show list of recent matters
    try:
        from themis.memory.session_store import list_sessions
        matters = list_sessions(limit=5, sessions_db=cfg.sessions_db)
    except Exception:
        matters = []

    if not matters:
        await update.message.reply_text(
            "No saved matters found. Send a brief to start a new one."
        )
        return

    await update.message.reply_text(
        "📂 *Your recent matters:*\nSelect one to resume:",
        reply_markup=_make_resume_keyboard(matters),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_matters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    args = context.args or []
    query = " ".join(args).strip()

    try:
        from themis.memory.session_store import search_sessions, list_sessions
        matters = search_sessions(query, limit=10, sessions_db=cfg.sessions_db) if query else list_sessions(limit=10, sessions_db=cfg.sessions_db)
    except Exception:
        matters = []

    if not matters:
        await update.message.reply_text("No matters found." + (f" (searched: '{query}')" if query else ""))
        return

    lines = ["📂 *Saved matters:*\n"]
    for m in matters:
        dt = (m.get("created_at") or "")[:10]
        lines.append(
            f"• `{m['matter_id']}` — {m.get('matter_type') or '?'} | {m.get('jurisdiction') or '?'} | {dt}"
        )
    lines.append("\nUse `/resume <matter_id>` to continue one.")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    from themis.gateway.setup_wizard import start_wizard
    session = _get_or_create_session(user.id, cfg)
    await start_wizard(update.message, session)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⚖️ *Themis Commands*\n\n"
        "/start — welcome message\n"
        "/new — start a fresh matter\n"
        "/resume — continue a previous matter\n"
        "/matters [query] — search saved matters\n"
        "/status — current matter info\n"
        "/reminder <matter\\_id> <YYYY-MM-DD> [note] — set a hearing reminder\n"
        "/reminders — list your pending reminders\n"
        "/setup — configure lawyer profile & API keys\n"
        "/help — this message\n\n"
        "Send any text to begin a matter brief.\n"
        "Send a PDF to get a contract risk report.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /reminder <matter_id> <YYYY-MM-DD> [note text]

    Examples:
      /reminder M-ABCD1234 2026-08-15
      /reminder M-ABCD1234 2026-08-15 HC hearing — injunction matter
    """
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/reminder <matter_id> <YYYY-MM-DD> [note]`\n"
            "Example: `/reminder M-ABCD1234 2026-08-15 Delhi HC hearing`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    matter_id = args[0]
    hearing_date = args[1]
    note = " ".join(args[2:]) if len(args) > 2 else ""

    try:
        from themis.scheduler.reminders import add_reminder_and_schedule
        rid = add_reminder_and_schedule(
            app=context.application,
            matter_id=matter_id,
            hearing_date=hearing_date,
            note=note,
            days_before=1,
            telegram_user_id=user.id,
            sessions_db=cfg.sessions_db,
            matters_dir=cfg.matters_dir,
        )
        await update.message.reply_text(
            f"⏰ *Reminder set!*\n"
            f"Matter: `{matter_id}`\n"
            f"Hearing: {hearing_date}\n"
            f"Note: {note or '—'}\n"
            f"You'll be reminded 1 day before. (Reminder ID: {rid})",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Could not set reminder: {e}")


async def cmd_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List the current user's pending hearing reminders."""
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    try:
        from themis.memory.session_store import list_reminders
        reminders = list_reminders(include_fired=False, sessions_db=cfg.sessions_db)
        # Filter to this user's reminders
        reminders = [r for r in reminders if str(r.get("telegram_user_id", "")) == str(user.id)]
    except Exception:
        reminders = []

    if not reminders:
        await update.message.reply_text(
            "You have no pending reminders.\n"
            "Use `/reminder <matter_id> <YYYY-MM-DD> [note]` to set one.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines = ["⏰ *Pending reminders:*\n"]
    for r in reminders:
        lines.append(
            f"• ID {r['id']} — `{r['matter_id']}` | Hearing: {r['hearing_date']} | "
            f"Fires: {r['fire_at'][:10]} | {r.get('note') or '—'}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Resume helper
# ---------------------------------------------------------------------------

async def _resume_matter(
    message: Message,
    user_id: int,
    matter_id: str,
    cfg: LexConfig,
) -> None:
    try:
        from themis.memory.session_store import get_session_state
        state = get_session_state(matter_id, sessions_db=cfg.sessions_db)
    except Exception:
        state = None

    if not state:
        await message.reply_text(f"❌ Matter `{matter_id}` not found.", parse_mode=ParseMode.MARKDOWN)
        return

    session = TelegramSession(
        matter_id=matter_id,
        graph_state=state,
        completed=bool(state.get("draft_output")),
    )
    _sessions[user_id] = session

    mt = state.get("matter_type") or "Unknown"
    jur = state.get("jurisdiction") or "Unknown"
    status = "✅ Complete" if session.completed else "🔄 In progress"

    await message.reply_text(
        f"📂 *Resumed matter `{matter_id}`*\n"
        f"Type: {mt}\nJurisdiction: {jur}\nStatus: {status}\n\n"
        f"{'Send a new message to continue.' if not session.completed else 'This matter is complete. Use /new to start fresh.'}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# Callback query handler (buttons)
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: LexConfig = context.bot_data["cfg"]
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    if not _is_allowed(user.id, cfg):
        return

    data = query.data or ""
    session = _get_or_create_session(user.id, cfg)

    # --- Resume a matter ---
    if data.startswith("resume:"):
        matter_id = data.split(":", 1)[1]
        await query.edit_message_text(f"📂 Loading matter `{matter_id}`…", parse_mode=ParseMode.MARKDOWN)
        await _resume_matter(query.message, user.id, matter_id, cfg)
        return

    # --- Intake question answers ---
    if data.startswith("ans:"):
        parts = data.split(":", 2)
        if len(parts) != 3:
            return
        _, field, value_raw = parts

        if value_raw == "other":
            # Ask user to type their answer
            session.awaiting_free_text_for = field
            await query.edit_message_text(f"✏️ Please type your answer for: *{field}*", parse_mode=ParseMode.MARKDOWN)
            return

        # Map option index back to text if it's a number
        # (The full options list isn't in callback_data, so we store it in pending_questions)
        # If value_raw is "yes"/"no" it's binary — use directly
        value = value_raw
        if value_raw.isdigit():
            # Find the question in graph_state to resolve option index
            qs = (session.graph_state or {}).get("pending_questions") or []
            for q in qs:
                if q.get("field") == field:
                    opts = q.get("options", [])
                    idx = int(value_raw)
                    if idx < len(opts):
                        value = opts[idx]
                    break

        # Edit the button message to show the answer
        await query.edit_message_text(f"✅ {field}: *{value}*", parse_mode=ParseMode.MARKDOWN)

        # Merge answer into session state
        if session.graph_state is None:
            session.graph_state = {}
        # WHY: parties is typed Optional[dict] in LexState; storing a raw string causes
        # 'str' object has no attribute 'get' when downstream nodes call parties.get().
        if field == "parties" and isinstance(value, str):
            value = {"description": value}
        session.graph_state[field] = value

        # Continue: send next question or trigger the graph
        if session.pending_questions:
            await _send_next_question(query.message, session)
        else:
            # All queued questions answered — re-run the graph to check intake completion
            brief = session.graph_state.get("user_input", "continue")
            await _run_graph_for_user(
                user_id=user.id,
                message=query.message,
                cfg=cfg,
                initial_brief=brief,
            )
        return

    # --- Tool routing selection ---
    if data.startswith("tool:"):
        tool = data.split(":", 1)[1]

        if session.graph_state is None:
            session.graph_state = {}

        approved = session.graph_state.get("approved_tools") or []
        if tool == "skip":
            session.graph_state["approved_tools"] = []
            session.tools_approved = True
            await query.edit_message_text("⏭ Skipping research. Drafting directly from brief…")
        elif tool == "ecourts":
            # Toggle eCourts nudge — check if configured
            if cfg.ecourts_backend == "stub":
                await query.edit_message_text(
                    "⚠️ eCourts MCP is not yet configured.\n\n"
                    "Run /setup and choose *Enable MCP tools → eCourts MCP* to connect it.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return
            approved.append("ecourts")
            session.graph_state["approved_tools"] = approved
            await query.edit_message_text(f"✅ Tools selected: {', '.join(approved)}\n\nStarting research…")
            session.tools_approved = True
        else:
            approved.append(tool)
            session.graph_state["approved_tools"] = approved
            await query.edit_message_text(
                f"✅ *{tool}* added.\n\nSelect more sources or proceed:",
                reply_markup=_make_tool_routing_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        if session.tools_approved:
            brief = session.graph_state.get("user_input", "continue")
            await _run_graph_for_user(
                user_id=user.id,
                message=query.message,
                cfg=cfg,
                initial_brief=brief,
            )
        return

    # --- Confirm tool selection and proceed ---
    if data == "tool:proceed":
        session.tools_approved = True
        brief = (session.graph_state or {}).get("user_input", "continue")
        await query.edit_message_text("⚖️ Starting research…")
        await _run_graph_for_user(
            user_id=user.id,
            message=query.message,
            cfg=cfg,
            initial_brief=brief,
        )
        return

    # --- Post-draft actions ---
    if data.startswith("action:"):
        action = data.split(":", 1)[1]
        await _handle_post_draft_action(query, user.id, action, session, cfg)
        return

    # --- Setup wizard buttons ---
    if data.startswith("setup:"):
        from themis.gateway.setup_wizard import handle_wizard_callback
        await handle_wizard_callback(query, session, cfg)
        return


async def _handle_post_draft_action(
    query,
    user_id: int,
    action: str,
    session: TelegramSession,
    cfg: LexConfig,
) -> None:
    state = session.graph_state or {}

    if action == "done":
        await query.edit_message_text("✅ All done! Use /new to start another matter.")
        return

    if action == "redraft":
        await query.edit_message_text("↩ Redrafting… Send any additional instructions below, or just say 'redraft' to use the same brief.")
        session.completed = False
        session.awaiting_post_draft_input = "redraft"
        return

    if action == "email":
        await query.edit_message_text("📧 Enter the recipient's email address:")
        session.awaiting_post_draft_input = "email_recipient"
        return

    if action == "drive":
        await query.edit_message_text("💾 Uploading to Google Drive…")
        try:
            from themis.gateway.integrations import upload_to_drive
            result = await upload_to_drive(state, cfg)
            await query.message.reply_text(f"✅ Uploaded: {result}")
        except NotImplementedError as e:
            await query.message.reply_text(f"⚙️ *Not configured yet*\n{e}\n\nUse /setup to enable Google Drive.", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await query.message.reply_text(f"❌ Drive upload failed: {e}")
        return

    if action == "ecourts":
        await query.edit_message_text("⚖️ Searching eCourts for related cases…")
        try:
            from themis.gateway.integrations import lookup_ecourts
            result = await lookup_ecourts(state, cfg)
            await query.message.reply_text(result)
        except NotImplementedError as e:
            await query.message.reply_text(f"⚙️ *Not configured yet*\n{e}\n\nUse /setup to enable eCourts MCP.", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await query.message.reply_text(f"❌ eCourts lookup failed: {e}")
        return

    if action == "forward":
        await query.edit_message_text("👤 Enter the Telegram user ID or @username to forward the draft to:")
        session.awaiting_post_draft_input = "forward_recipient"
        return

    if action == "docusign":
        await query.edit_message_text("🔏 DocuSign integration — enter recipient email for signing request:")
        session.awaiting_post_draft_input = "docusign_recipient"
        return


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    session = _get_or_create_session(user.id, cfg)
    text = update.message.text or ""

    # --- Setup wizard intercept ---
    if session.in_setup:
        from themis.gateway.setup_wizard import handle_wizard_text
        await handle_wizard_text(update.message, session, cfg)
        return

    # --- Post-draft action input ---
    if session.awaiting_post_draft_input:
        await _handle_post_draft_text_input(update.message, session, cfg, text)
        return

    # --- Inline keyboard follow-up: user typed instead of clicking ---
    if session.awaiting_free_text_for:
        field = session.awaiting_free_text_for
        session.awaiting_free_text_for = None

        if session.graph_state is None:
            session.graph_state = {}
        # parties is typed Optional[dict]; wrap plain strings to avoid downstream .get() crash
        if field == "parties" and isinstance(text, str):
            session.graph_state[field] = {"description": text}
        else:
            session.graph_state[field] = text

        await update.message.reply_text(f"✅ Got it: *{text}*", parse_mode=ParseMode.MARKDOWN)

        if session.pending_questions:
            await _send_next_question(update.message, session)
        else:
            brief = session.graph_state.get("user_input", text)
            await _run_graph_for_user(user_id=user.id, message=update.message, cfg=cfg, initial_brief=brief)
        return

    # --- Auto-detect matter ID references and load existing state ---
    await _try_load_matter(user.id, text, session, cfg, update.message)
    # Re-fetch session after potential update
    session = _get_or_create_session(user.id, cfg)

    # --- Normal matter brief: first check tool routing ---
    if (
        session.graph_state
        and session.graph_state.get("intake_complete")
        and not session.tools_approved
        and not session.completed
    ):
        # Intake complete but tools not selected yet — show routing menu
        await _send_tool_routing(update.message)
        return

    # --- Standard graph invocation ---
    await _run_graph_for_user(
        user_id=user.id,
        message=update.message,
        cfg=cfg,
        initial_brief=text,
        workflow_mode="draft",
    )


async def _handle_post_draft_text_input(
    message: Message,
    session: TelegramSession,
    cfg: LexConfig,
    text: str,
) -> None:
    action = session.awaiting_post_draft_input
    session.awaiting_post_draft_input = None
    state = session.graph_state or {}

    if action == "email_recipient":
        await message.reply_text(f"📧 Drafting email to {text}…")
        try:
            from themis.gateway.integrations import send_draft_email
            result = await send_draft_email(state, recipient=text, cfg=cfg)
            await message.reply_text(f"✅ {result}")
        except NotImplementedError as e:
            await message.reply_text(f"⚙️ *Not configured yet*\n{e}\n\nUse /setup to enable Gmail MCP.", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await message.reply_text(f"❌ Email failed: {e}")

    elif action == "forward_recipient":
        await message.reply_text(f"👤 Forwarding draft to {text}…")
        try:
            from themis.gateway.integrations import forward_draft
            await forward_draft(state, recipient=text, bot=message.get_bot(), cfg=cfg)
            await message.reply_text("✅ Draft forwarded.")
        except Exception as e:
            await message.reply_text(f"❌ Forward failed: {e}")

    elif action == "docusign_recipient":
        await message.reply_text(f"🔏 Sending DocuSign request to {text}…")
        try:
            from themis.gateway.integrations import send_docusign
            result = await send_docusign(state, recipient=text, cfg=cfg)
            await message.reply_text(f"✅ {result}")
        except NotImplementedError as e:
            await message.reply_text(f"⚙️ *Not configured yet*\n{e}", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await message.reply_text(f"❌ DocuSign failed: {e}")

    elif action == "redraft":
        # Use the typed text as additional instruction for redraft
        brief = text if text.lower() != "redraft" else (state.get("user_input") or "redraft")
        await _run_graph_for_user(
            user_id=message.chat_id,
            message=message,
            cfg=cfg,
            initial_brief=brief,
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle PDF uploads — triggers contract review workflow."""
    cfg: LexConfig = context.bot_data["cfg"]
    user = update.effective_user
    if not _is_allowed(user.id, cfg):
        await update.message.reply_text("Sorry, you are not authorised to use this bot.")
        return

    doc: Document = update.message.document
    if not doc.mime_type or "pdf" not in doc.mime_type.lower():
        await update.message.reply_text("Please send a PDF file for contract review.")
        return

    await update.message.reply_text(f"📄 Received: {doc.file_name}\nDownloading…")

    tg_file = await context.bot.get_file(doc.file_id)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    await tg_file.download_to_drive(tmp_path)

    _sessions[user.id] = TelegramSession(matter_id=f"M-{uuid.uuid4().hex[:8].upper()}")

    await _run_graph_for_user(
        user_id=user.id,
        message=update.message,
        cfg=cfg,
        initial_brief=f"Review contract: {doc.file_name}",
        workflow_mode="contract_review",
        contract_upload_path=tmp_path,
    )

    try:
        os.unlink(tmp_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Dynamic skill command registration
# ---------------------------------------------------------------------------

async def _register_skill_commands(application) -> None:
    """
    Register dynamic slash commands from the skills manifest at bot startup.
    WHY: Adding a new .md skill file automatically makes its Telegram command available
    without any code change — bot.set_my_commands() replaces the list atomically.
    """
    from themis.skills.loader import build_skills_manifest

    cfg: LexConfig = application.bot_data.get("cfg") or LexConfig()
    bundled_dir = Path(__file__).parent.parent / "skills"
    user_dir = Path(cfg.skills_dir).expanduser()
    manifest = build_skills_manifest(bundled_dir, user_dir)

    from telegram import BotCommand

    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help"),
        BotCommand("draft", "Draft a legal document"),
        BotCommand("skill_list", "List available skills"),
        BotCommand("skill", "Load a skill by name: /skill <name>"),
    ]

    for name, desc in manifest.items():
        cmd_name = name[:32].lower()
        short_desc = (desc[:256] if desc else f"Load {name} skill")
        commands.append(BotCommand(cmd_name, short_desc))

    try:
        await application.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("Failed to register Telegram commands: %s", e)


# ---------------------------------------------------------------------------
# Bot runner
# ---------------------------------------------------------------------------

def run_telegram_bot(cfg: Optional[LexConfig] = None) -> None:
    if cfg is None:
        cfg = LexConfig()

    token = cfg.telegram_bot_token
    if not token:
        console.print(
            "[red]TELEGRAM_BOT_TOKEN is not set.[/red] "
            "Add it to .env or run /setup in Telegram."
        )
        raise SystemExit(1)

    console.print("[bold cyan]⚖ Themis Telegram Gateway — Phase 8[/bold cyan]")
    console.print("Starting long-polling bot…")

    if cfg.telegram_allowed_users:
        console.print(f"Allowlist: {cfg.telegram_allowed_users}")
    else:
        console.print("[yellow]No allowlist set — all users can interact.[/yellow]")

    # Phase 9: set up LangGraph Postgres checkpoint tables (idempotent, no-op if no Postgres URL).
    asyncio.run(setup_checkpointer(cfg))
    get_graph(cfg)
    console.print("[green]Graph compiled and ready.[/green]")

    async def _post_init(application) -> None:
        await _register_skill_commands(application)

    app = Application.builder().token(token).post_init(_post_init).build()
    app.bot_data["cfg"] = cfg

    # --- /skill_list and /skill handlers ---

    async def handle_skill_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Reply with a formatted list of all available skills."""
        _cfg: LexConfig = context.bot_data["cfg"]
        bundled_dir = Path(__file__).parent.parent / "skills"
        user_dir = Path(_cfg.skills_dir).expanduser()
        from themis.skills.loader import build_skills_manifest
        manifest = build_skills_manifest(bundled_dir, user_dir)

        if not manifest:
            await update.message.reply_text("No skills available.")
            return

        lines = ["*Available Skills:*\n"]
        for name, desc in sorted(manifest.items()):
            lines.append(f"• `{name}` — {desc or 'no description'}")
        lines.append("\nUse `/skill <name>` to force-load a skill on your next draft.")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def handle_skill_load(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /skill <name> — store skill name in user_data so the next draft uses it.
        Additive: calling /skill again adds to the forced set.
        """
        args = context.args
        if not args:
            await update.message.reply_text(
                "Usage: `/skill <name>`\nExample: `/skill bail_application`\n\n"
                "Run `/skill_list` to see all available skills.",
                parse_mode="Markdown",
            )
            return

        skill_name = args[0].strip()

        _cfg: LexConfig = context.bot_data["cfg"]
        bundled_dir = Path(__file__).parent.parent / "skills"
        user_dir = Path(_cfg.skills_dir).expanduser()
        from themis.skills.loader import build_skills_manifest
        manifest = build_skills_manifest(bundled_dir, user_dir)

        if skill_name not in manifest:
            close = [n for n in manifest if skill_name in n or n in skill_name]
            hint = f"\n\nDid you mean: `{'`, `'.join(close[:3])}`?" if close else ""
            await update.message.reply_text(
                f"Skill `{skill_name}` not found.{hint}\n\nRun `/skill_list` to see all available skills.",
                parse_mode="Markdown",
            )
            return

        forced: list = context.user_data.get("forced_skill_names", [])
        if skill_name not in forced:
            forced.append(skill_name)
        context.user_data["forced_skill_names"] = forced

        await update.message.reply_text(
            f"✓ Skill `{skill_name}` queued for your next draft.\n"
            f"Current forced skills: `{', '.join(forced)}`\n\n"
            "Send your matter brief to proceed.",
            parse_mode="Markdown",
        )

    app.add_handler(CommandHandler("skill_list", handle_skill_list))
    app.add_handler(CommandHandler("skill", handle_skill_load))

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("matters", cmd_matters))
    app.add_handler(CommandHandler("reminder", cmd_reminder))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("setup", cmd_setup))
    app.add_handler(CommandHandler("help", cmd_help))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Text + document
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))

    # Phase 8: schedule any pending hearing reminders from SQLite on startup.
    # WHY: python-telegram-bot's JobQueue is ephemeral — all jobs are lost on restart.
    # Re-scheduling on startup ensures reminders survive bot crashes/restarts.
    try:
        from themis.scheduler.reminders import schedule_pending_reminders
        n = schedule_pending_reminders(app, sessions_db=cfg.sessions_db, matters_dir=cfg.matters_dir)
        if n:
            console.print(f"[cyan]Scheduled {n} pending reminder(s).[/cyan]")
    except Exception as e:
        console.print(f"[yellow]Could not schedule reminders: {e}[/yellow]")

    console.print("[bold green]Bot is running. Press Ctrl+C to stop.[/bold green]")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
