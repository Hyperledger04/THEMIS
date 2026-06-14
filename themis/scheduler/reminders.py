# Hearing reminder scheduler for Themis.
#
# WHY: Uses python-telegram-bot's built-in JobQueue (backed by APScheduler) when
# the Telegram bot is running. For CLI-only usage, reminders are stored in SQLite
# and surfaced as a list — no separate process needed.
#
# Flow:
#   1. Lawyer sets a hearing reminder via `lex reminder add` or the Telegram /reminder command.
#   2. Reminder is stored in the `reminders` table in sessions.db with a fire_at timestamp.
#   3. On bot startup, `schedule_pending_reminders(app)` reads all unfired reminders and
#      registers them with the job_queue so they fire at the right time.
#   4. When fired, the job sends a Telegram message to the lawyer with the last 500 chars of
#      the matter's MEMORY.md for context.

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from telegram.ext import Application


def _build_reminder_message(matter_id: str, note: str, hearing_date: str, matters_dir: str) -> str:
    """Build the reminder message text, injecting the last 500 chars of MEMORY.md."""
    matter_path = Path(matters_dir).expanduser() / matter_id / "MEMORY.md"
    context_snippet = ""
    if matter_path.exists():
        full_text = matter_path.read_text(encoding="utf-8")
        context_snippet = full_text[-500:].strip()

    lines = [
        f"⏰ *Hearing reminder — {hearing_date}*",
        f"Matter: `{matter_id}`",
    ]
    if note:
        lines.append(f"Note: {note}")
    if context_snippet:
        lines.append(f"\n_Recent context from matter memory:_\n```\n{context_snippet}\n```")
    lines.append("\nUse /matters to view the full matter file.")
    return "\n".join(lines)


async def _fire_reminder(context) -> None:
    """Job callback: send the reminder message and mark it fired in SQLite."""
    job_data = context.job.data
    reminder_id: int = job_data["reminder_id"]
    telegram_user_id: int = job_data["telegram_user_id"]
    matter_id: str = job_data["matter_id"]
    note: str = job_data.get("note", "")
    hearing_date: str = job_data["hearing_date"]
    sessions_db: str = job_data["sessions_db"]
    matters_dir: str = job_data["matters_dir"]

    text = _build_reminder_message(matter_id, note, hearing_date, matters_dir)

    try:
        await context.bot.send_message(
            chat_id=telegram_user_id,
            text=text,
            parse_mode="Markdown",
        )
    finally:
        from themis.memory.session_store import mark_reminder_fired
        mark_reminder_fired(reminder_id, sessions_db)


def schedule_pending_reminders(app: "Application", sessions_db: str, matters_dir: str) -> int:
    """
    On bot startup: load all unfired reminders from SQLite and register them
    with the job_queue so they fire at the correct time.

    WHY: python-telegram-bot's JobQueue is ephemeral — jobs are lost on restart.
    By re-scheduling all pending reminders on every startup we get persistence
    without a separate APScheduler job store.

    Returns the number of reminders scheduled.
    """
    from themis.memory.session_store import get_due_reminders, list_reminders

    # All unfired reminders (both due and future)
    try:
        from themis.memory.session_store import init_db
        init_db(sessions_db)
    except Exception:
        pass

    from themis.memory.session_store import list_reminders
    pending = list_reminders(include_fired=False, sessions_db=sessions_db)

    now = datetime.now()
    scheduled = 0

    for r in pending:
        if not r.get("telegram_user_id"):
            continue  # CLI-added reminder with no Telegram user — skip job scheduling

        try:
            fire_at = datetime.fromisoformat(r["fire_at"])
        except (ValueError, TypeError):
            continue

        job_data = {
            "reminder_id": r["id"],
            "telegram_user_id": int(r["telegram_user_id"]),
            "matter_id": r["matter_id"],
            "note": r.get("note", ""),
            "hearing_date": r["hearing_date"],
            "sessions_db": sessions_db,
            "matters_dir": matters_dir,
        }

        if fire_at <= now:
            # Already due — fire immediately (1 second from now)
            from datetime import timedelta
            app.job_queue.run_once(_fire_reminder, when=1, data=job_data, name=f"reminder_{r['id']}")
        else:
            app.job_queue.run_once(_fire_reminder, when=fire_at, data=job_data, name=f"reminder_{r['id']}")

        scheduled += 1

    return scheduled


def add_reminder_and_schedule(
    app: "Application",
    matter_id: str,
    hearing_date: str,
    note: str,
    days_before: int,
    telegram_user_id: Optional[int],
    sessions_db: str,
    matters_dir: str,
) -> int:
    """
    Add a reminder to SQLite AND register it with the running job_queue immediately.
    Returns the new reminder ID.

    WHY: Call this from the Telegram bot when a user sets a reminder via /reminder.
    It keeps SQLite and the job_queue in sync without needing a restart.
    """
    from themis.memory.session_store import add_reminder

    uid_str = str(telegram_user_id) if telegram_user_id else None
    reminder_id = add_reminder(
        matter_id=matter_id,
        hearing_date=hearing_date,
        note=note,
        days_before=days_before,
        telegram_user_id=uid_str,
        sessions_db=sessions_db,
    )

    if app is not None and telegram_user_id is not None:
        from datetime import timedelta
        from themis.memory.session_store import get_due_reminders, list_reminders

        # Fetch the just-added reminder to get its fire_at
        reminders = list_reminders(matter_id=matter_id, include_fired=False, sessions_db=sessions_db)
        target = next((r for r in reminders if r["id"] == reminder_id), None)
        if target:
            try:
                fire_at = datetime.fromisoformat(target["fire_at"])
            except (ValueError, TypeError):
                fire_at = datetime.now()

            job_data = {
                "reminder_id": reminder_id,
                "telegram_user_id": telegram_user_id,
                "matter_id": matter_id,
                "note": note,
                "hearing_date": hearing_date,
                "sessions_db": sessions_db,
                "matters_dir": matters_dir,
            }
            when = fire_at if fire_at > datetime.now() else 1
            app.job_queue.run_once(
                _fire_reminder,
                when=when,
                data=job_data,
                name=f"reminder_{reminder_id}",
            )

    return reminder_id
