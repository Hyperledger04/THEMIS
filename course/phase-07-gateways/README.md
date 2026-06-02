# Phase 7 — Gateways: CLI + Telegram

> **Status: Coming soon.** Complete Phases 0-6 first.

## What you will build

By the end of this phase, your agent will:
- Accept briefs from the terminal (`lex draft "..."`)
- Accept briefs from Telegram with inline button responses
- Stream LLM output token-by-token to both interfaces
- Route identical graph invocations regardless of which gateway sent the message

## The files you will understand

- `lexagent/cli.py` — Typer app, all commands (`draft`, `chat`, `agent`, `contract`, ...)
- `lexagent/gateway/telegram.py` — `run_telegram_bot()`, `_run_graph_for_user()`
- `lexagent/gateway/control_plane.py` — FastAPI server, webhook endpoint
- `lexagent/gateway/voice.py` — WebSocket + Twilio voice gateway

## Key concepts

**Typer** — builds CLIs with type-annotated Python functions. Each function = one command.
```python
@app.command()
def draft(matter: str = typer.Argument(...)):
    asyncio.run(_run_draft(matter))
```

**python-telegram-bot** — async library for Telegram bots.
- `Application` processes updates
- `CommandHandler` maps `/start` to a function
- `CallbackQueryHandler` handles inline button presses
- `thread_id = str(user_id)` links graph state to user

**Gateway abstraction** — `_run_graph_for_user(user_id, message, cfg)` is the same function whether called from CLI, Telegram, or the API. The graph doesn't know which gateway called it.

**Inline buttons** — Phase 8 added structured intake: instead of free text, Telegram shows buttons. The `pending_questions` state field holds `{field, question, type: binary|mcq|open, options: [...]}` objects. The gateway renders them as `InlineKeyboardButton`.

## Coming in this phase

1. `01_typer_cli.py` — Typer basics, commands, options, async bridge
2. `02_telegram_bot.py` — python-telegram-bot from scratch
3. `03_inline_buttons.py` — structured intake with callback queries
4. `04_streaming.py` — streaming LLM tokens to terminal and Telegram
5. `exercises/ex01_add_cli_command.py` — add a new `lex` command
6. `exercises/ex02_telegram_handler.py` — add a Telegram command handler
