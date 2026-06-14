# In-Telegram setup wizard for Themis.
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
    from themis.gateway.telegram import TelegramSession
    from themis.config import LexConfig

# Wizard step definitions
_STEPS = [
    {
        "key": "name",
        "text": "👤 *Step 1 of 6: What is your full name?*\n(Used in document headers and SOUL.md)",
        "type": "open",
    },
    {
        "key": "bar_number",
        "text": "🪪 *Step 2 of 6: Bar enrollment number?*\n(Optional — used in vakalatnamas)",
        "type": "open_optional",
    },
    {
        "key": "primary_court",
        "text": "⚖️ *Step 3 of 6: Your primary court?*",
        "type": "mcq",
        "options": ["Delhi High Court", "Bombay High Court", "Madras High Court", "Supreme Court of India"],
    },
    {
        "key": "api_keys",
        "text": (
            "🔑 *Step 4 of 6: Configure API keys?*\n"
            "Select a key to add \\(you can add multiple\\):\n\n"
            "_Indian case law:_\n"
            "• Indian Kanoon API\n"
            "• eCourts MCP \\(needs dashboard key\\)\n\n"
            "_Web search:_\n"
            "• Tavily API\n"
            "• SerpAPI\n"
            "• Perplexity API\n"
            "• Firecrawl API\n\n"
            "_International:_\n"
            "• CourtListener \\(US\\)\n\n"
            "_LLM providers:_\n"
            "• OpenAI key\n"
            "• Anthropic key"
        ),
        "type": "multi_action",
        "options": [
            "Indian Kanoon API", "eCourts MCP (dashboard key)", "Tavily API",
            "SerpAPI", "Perplexity API", "Firecrawl API", "CourtListener (US)",
            "OpenAI key", "Anthropic key", "Skip",
        ],
    },
    {
        "key": "keyless_tools",
        "text": (
            "🔌 *Step 5 of 6: Enable keyless research tools?*\n"
            "These need no API key — just toggle on:\n\n"
            "• Playwright browser \\(scrapes Kanoon directly\\)\n"
            "• DuckDuckGo \\(free web search\\)\n"
            "• Jina Reader \\(verifies citation URLs\\)\n"
            "• legislation\\.gov\\.in \\(official statute portal\\)"
        ),
        "type": "multi_action",
        "options": ["Playwright browser", "DuckDuckGo", "Jina Reader", "legislation.gov.in", "All keyless", "Skip"],
    },
    {
        "key": "mcp_tools",
        "text": "🔌 *Step 6 of 6: Enable other MCP integrations?*\nSelect integrations to activate:",
        "type": "multi_action",
        "options": ["Gmail MCP", "Google Drive", "All of the above", "Skip"],
    },
]

# Maps wizard label → (env_flag_key, env_api_key, needs_message_delete, ecourts_backend)
_API_KEY_MAP = {
    "Indian Kanoon API":          ("LEX_ENABLE_KANOON=true",        "KANOON_API_KEY"),
    "eCourts MCP (dashboard key)": ("LEX_ECOURTS_BACKEND=api",      "ECOURTS_API_KEY"),
    "Tavily API":                  ("LEX_TAVILY_ENABLED=true",       "TAVILY_API_KEY"),
    "SerpAPI":                     ("LEX_SERPAPI_ENABLED=true",      "SERPAPI_API_KEY"),
    "Perplexity API":              ("LEX_PERPLEXITY_ENABLED=true",   "PERPLEXITY_API_KEY"),
    "Firecrawl API":               ("LEX_FIRECRAWL_ENABLED=true",    "FIRECRAWL_API_KEY"),
    "CourtListener (US)":          ("LEX_COURTLISTENER_ENABLED=true","COURTLISTENER_API_KEY"),
    "OpenAI key":                  (None,                            "OPENAI_API_KEY"),
    "Anthropic key":               (None,                            "ANTHROPIC_API_KEY"),
}

_KEYLESS_FLAG_MAP = {
    "Playwright browser":  "LEX_PLAYWRIGHT_ENABLED=true",
    "DuckDuckGo":          "LEX_WEB_SEARCH_ENABLED=true",
    "Jina Reader":         "LEX_JINA_ENABLED=true",
    "legislation.gov.in":  "LEX_LEGISLATION_ENABLED=true",
}


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
        current = session.setup_data.get("api_keys_collected", {})
        pending_key_name = session.setup_data.get("pending_api_key")
        if pending_key_name:
            current[pending_key_name] = text.strip()
            session.setup_data["api_keys_collected"] = current
            await message.reply_text("✅ Key saved (message deleted for security).")
        # Stay on the api_keys step so user can add more keys; step advances on Skip
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

        # API key tools — prompt for the key (with eCourts dashboard hint)
        if value in _API_KEY_MAP:
            session.setup_data["pending_api_key"] = value
            hint = ""
            if value == "eCourts MCP (dashboard key)":
                hint = "\n\n🌐 Get your key at: https://api.ecourts.gov.in/dashboard"
            await query.edit_message_text(
                f"🔑 Enter your *{value}* key:{hint}\n_(This message will be deleted immediately after you send it)_",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Keyless tools toggle
        if key == "keyless_tools":
            tools = session.setup_data.get("keyless_tools", [])
            if value == "All keyless":
                tools = list(_KEYLESS_FLAG_MAP.keys())
            elif value not in tools:
                tools.append(value)
            session.setup_data["keyless_tools"] = tools
            await query.edit_message_text(
                f"✅ Enabled: {', '.join(tools)}\n\nSelect more or choose *Skip* to finish.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Done", callback_data="setup:action:Skip")
                ]]),
            )
            return

        if key == "mcp_tools":
            tools = session.setup_data.get("mcp_tools", [])
            if value == "All of the above":
                tools = ["Gmail MCP", "Google Drive"]
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

    home = Path("~/.themis").expanduser()
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

    # Write API keys and tool enable flags to ~/.themis/.env
    api_keys = data.get("api_keys_collected", {})
    keyless_tools = data.get("keyless_tools", [])
    lex_env_path = home / ".env"
    existing = lex_env_path.read_text(encoding="utf-8") if lex_env_path.exists() else ""
    additions: list[str] = []

    for label, (flag_line, api_env_var) in _API_KEY_MAP.items():
        if label in api_keys:
            # Write the enable flag
            if flag_line and flag_line.split("=")[0] not in existing:
                additions.append(flag_line)
            # Write the API key
            if api_env_var and api_env_var not in existing:
                additions.append(f"{api_env_var}={api_keys[label]}")

    for tool_label in keyless_tools:
        flag_line = _KEYLESS_FLAG_MAP.get(tool_label, "")
        if flag_line and flag_line.split("=")[0] not in existing:
            additions.append(flag_line)

    if additions:
        with lex_env_path.open("a", encoding="utf-8") as f:
            f.write(("\n" if existing and not existing.endswith("\n") else "") + "\n".join(additions) + "\n")

    # Also write MCP tool flags to SOUL.md (existing behaviour kept)

    summary_lines = ["✅ *Setup complete!*\n"]
    if data.get("name"):
        summary_lines.append(f"Name: {data['name']}")
    if data.get("primary_court"):
        summary_lines.append(f"Primary court: {data['primary_court']}")
    if api_keys:
        summary_lines.append(f"Research tools configured: {', '.join(api_keys.keys())}")
    if keyless_tools:
        summary_lines.append(f"Keyless tools enabled: {', '.join(keyless_tools)}")
    if data.get("mcp_tools"):
        summary_lines.append(f"MCP integrations: {', '.join(data['mcp_tools'])}")
    summary_lines.append("\nSend a matter brief to begin drafting!")

    await message.reply_text("\n".join(summary_lines), parse_mode=ParseMode.MARKDOWN)
