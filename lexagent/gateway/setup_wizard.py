# In-Telegram setup wizard for LexAgent.
#
# Triggered by /setup. Multi-step flow that configures:
#   1. Lawyer name
#   2. Bar enrollment number
#   3. Primary court (MCQ)
#   4. API keys (Indian Kanoon, OpenAI, Anthropic)
#   5. MCP tool toggles (eCourts, Gmail, Google Drive)
#
# WHY: The entire configuration flow runs inside Telegram — lawyers never need to touch
# a terminal, .env file, or SSH session. Sensitive inputs (API keys) are deleted immediately
# after reading so they don't sit in chat history.

from pathlib import Path
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode

if TYPE_CHECKING:
    from lexagent.gateway.telegram import TelegramSession
    from lexagent.config import LexConfig

# Wizard step definitions
_STEPS = [
    {
        "key": "name",
        "text": "👤 *Step 1 of 5: What is your full name?*\n(Used in document headers and SOUL.md)",
        "type": "open",
    },
    {
        "key": "bar_number",
        "text": "🪪 *Step 2 of 5: Bar enrollment number?*\n(Optional — used in vakalatnamas)",
        "type": "open_optional",
    },
    {
        "key": "primary_court",
        "text": "⚖️ *Step 3 of 5: Your primary court?*",
        "type": "mcq",
        "options": ["Delhi High Court", "Bombay High Court", "Madras High Court", "Supreme Court of India"],
    },
    {
        "key": "api_keys",
        "text": "🔑 *Step 4 of 5: Configure API keys?*\nSelect which key to add (you can add multiple):",
        "type": "multi_action",
        "options": ["Indian Kanoon API", "OpenAI key", "Anthropic key", "Skip"],
    },
    {
        "key": "mcp_tools",
        "text": "🔌 *Step 5 of 5: Enable MCP tools?*\nSelect integrations to activate:",
        "type": "multi_action",
        "options": ["eCourts MCP", "Gmail MCP", "Google Drive", "All of the above", "Skip"],
    },
]


async def start_wizard(message: Message, session: "TelegramSession") -> None:
    """Begin the setup wizard — reset state and send step 1."""
    session.in_setup = True
    session.setup_step = 0
    session.setup_data = {}
    await _send_step(message, session)


async def _send_step(message: Message, session: "TelegramSession") -> None:
    step_idx = session.setup_step
    if step_idx >= len(_STEPS):
        await _finish_wizard(message, session)
        return

    step = _STEPS[step_idx]
    text = step["text"]
    stype = step["type"]

    if stype == "open" or stype == "open_optional":
        skip_row = [[InlineKeyboardButton("⏭ Skip", callback_data="setup:skip")]] if stype == "open_optional" else []
        markup = InlineKeyboardMarkup(skip_row) if skip_row else None
        if markup:
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
        else:
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    elif stype == "mcq":
        options = step.get("options", [])
        rows = [[InlineKeyboardButton(opt, callback_data=f"setup:mcq:{opt}")] for opt in options]
        rows.append([InlineKeyboardButton("✏️ Other — type below", callback_data="setup:mcq:other")])
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(rows))

    elif stype == "multi_action":
        options = step.get("options", [])
        rows = [[InlineKeyboardButton(opt, callback_data=f"setup:action:{opt}")] for opt in options]
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(rows))


async def handle_wizard_text(message: Message, session: "TelegramSession", cfg: "LexConfig") -> None:
    """Handle free-text input during the setup wizard."""
    step_idx = session.setup_step
    if step_idx >= len(_STEPS):
        return

    step = _STEPS[step_idx]
    key = step["key"]
    text = message.text or ""

    # If this is an API key step, delete the message immediately for security
    if key == "api_keys":
        try:
            await message.delete()
        except Exception:
            pass
        # Store the raw key value — will be written to .env
        current = session.setup_data.get("api_keys_collected", {})
        pending_key_name = session.setup_data.get("pending_api_key")
        if pending_key_name:
            current[pending_key_name] = text.strip()
            session.setup_data["api_keys_collected"] = current
            await message.reply_text(f"✅ Key saved (message deleted for security).")
        session.setup_step += 1
        await _send_step(message, session)
        return

    session.setup_data[key] = text.strip()
    await message.reply_text(f"✅ Saved: *{text.strip()[:40]}*", parse_mode=ParseMode.MARKDOWN)
    session.setup_step += 1
    await _send_step(message, session)


async def handle_wizard_callback(query, session: "TelegramSession", cfg: "LexConfig") -> None:
    """Handle inline button presses during the setup wizard."""
    await query.answer()
    data = query.data or ""
    step_idx = session.setup_step
    if step_idx >= len(_STEPS):
        return

    step = _STEPS[step_idx]
    key = step["key"]

    if data == "setup:skip":
        await query.edit_message_text(f"⏭ Skipped {key}.")
        session.setup_step += 1
        await _send_step(query.message, session)
        return

    if data.startswith("setup:mcq:"):
        value = data.split("setup:mcq:", 1)[1]
        if value == "other":
            await query.edit_message_text(f"✏️ Type your answer for *{key}*:", parse_mode=ParseMode.MARKDOWN)
            return
        session.setup_data[key] = value
        await query.edit_message_text(f"✅ {key}: *{value}*", parse_mode=ParseMode.MARKDOWN)
        session.setup_step += 1
        await _send_step(query.message, session)
        return

    if data.startswith("setup:action:"):
        value = data.split("setup:action:", 1)[1]

        if value == "Skip":
            await query.edit_message_text(f"⏭ Skipped {key}.")
            session.setup_step += 1
            await _send_step(query.message, session)
            return

        if value in ("Indian Kanoon API", "OpenAI key", "Anthropic key"):
            session.setup_data["pending_api_key"] = value
            await query.edit_message_text(
                f"🔑 Enter your *{value}*:\n_(This message will be deleted immediately after you send it)_",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        if key == "mcp_tools":
            tools = session.setup_data.get("mcp_tools", [])
            if value == "All of the above":
                tools = ["eCourts MCP", "Gmail MCP", "Google Drive"]
            else:
                if value not in tools:
                    tools.append(value)
            session.setup_data["mcp_tools"] = tools
            await query.edit_message_text(
                f"✅ Enabled: {', '.join(tools)}\n\nSelect more or choose *Skip* to finish.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Done", callback_data="setup:action:Skip")
                ]]),
            )
            return


async def _finish_wizard(message: Message, session: "TelegramSession") -> None:
    """Write collected wizard data to SOUL.md and .env, then exit wizard mode."""
    data = session.setup_data
    session.in_setup = False

    home = Path("~/.lexagent").expanduser()
    home.mkdir(parents=True, exist_ok=True)

    # Write SOUL.md
    soul_lines = ["# Lawyer Profile\n"]
    if data.get("name"):
        soul_lines.append(f"name: {data['name']}")
    if data.get("bar_number"):
        soul_lines.append(f"bar_number: {data['bar_number']}")
    if data.get("primary_court"):
        soul_lines.append(f"preferred_court: {data['primary_court']}")
    if data.get("mcp_tools"):
        soul_lines.append(f"enabled_mcp: {', '.join(data['mcp_tools'])}")

    soul_path = home / "SOUL.md"
    soul_path.write_text("\n".join(soul_lines) + "\n", encoding="utf-8")

    # Write API keys to .env
    api_keys = data.get("api_keys_collected", {})
    env_path = Path(".env")
    key_map = {
        "Indian Kanoon API": "KANOON_API_KEY",
        "OpenAI key": "OPENAI_API_KEY",
        "Anthropic key": "ANTHROPIC_API_KEY",
    }
    if api_keys:
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        additions = []
        for label, env_var in key_map.items():
            if label in api_keys:
                value = api_keys[label]
                if env_var not in existing:
                    additions.append(f"{env_var}={value}")
        if additions:
            with env_path.open("a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(additions) + "\n")

    summary_lines = ["✅ *Setup complete!*\n"]
    if data.get("name"):
        summary_lines.append(f"Name: {data['name']}")
    if data.get("primary_court"):
        summary_lines.append(f"Primary court: {data['primary_court']}")
    if data.get("mcp_tools"):
        summary_lines.append(f"MCP tools enabled: {', '.join(data['mcp_tools'])}")
    if api_keys:
        summary_lines.append(f"API keys saved: {', '.join(api_keys.keys())}")
    summary_lines.append("\nSend a matter brief to begin drafting!")

    await message.reply_text("\n".join(summary_lines), parse_mode=ParseMode.MARKDOWN)
