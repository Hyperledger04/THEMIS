# Post-draft integration actions: Gmail, Google Drive, eCourts lookup, forward, DocuSign.
# These are called from telegram.py callback handlers after a draft is complete.
#
# Each function is async and returns a human-readable result string.
# MCP tools are invoked directly where available; stubs raise NotImplementedError otherwise.

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lexagent.config import LexConfig


async def send_draft_email(state: dict, recipient: str, cfg: "LexConfig") -> str:
    """Send the draft as an email via Gmail MCP (mcp__claude_ai_Gmail__create_draft)."""
    draft = state.get("draft_output") or state.get("contract_review_output") or ""
    matter_id = state.get("matter_id") or ""
    matter_type = state.get("matter_type") or "Legal Document"
    subject = f"Draft: {matter_type} — Matter {matter_id}"

    # WHY: Gmail MCP is available via claude.ai integration. In production this should
    # call the MCP tool directly. For now, returns a confirmation stub that can be
    # replaced with an actual MCP call when the Telegram bot is wired to an MCP client.
    raise NotImplementedError(
        "Gmail MCP integration requires an MCP client connection. "
        "Configure Gmail MCP in /setup and restart the bot."
    )


async def upload_to_drive(state: dict, cfg: "LexConfig") -> str:
    """Upload the draft .docx to Google Drive via Google Drive MCP."""
    raise NotImplementedError(
        "Google Drive MCP integration requires an MCP client connection. "
        "Configure Google Drive in /setup and restart the bot."
    )


async def lookup_ecourts(state: dict, cfg: "LexConfig") -> str:
    """Look up related cases on eCourts using the eCourts MCP server."""
    if cfg.ecourts_backend == "stub":
        raise NotImplementedError(
            "eCourts MCP is not configured. Run /setup and enable eCourts MCP."
        )
    matter_type = state.get("matter_type") or ""
    parties = state.get("parties") or {}
    # Placeholder — replace with mcp__claude_ai_E-courts__search_cases call
    return f"eCourts lookup for '{matter_type}' — {parties}. Configure eCourts MCP for live results."


async def forward_draft(state: dict, recipient: str, bot: Any, cfg: "LexConfig") -> None:
    """Forward the draft text to another Telegram user."""
    draft = state.get("draft_output") or state.get("contract_review_output") or ""
    if not draft:
        raise ValueError("No draft to forward.")
    # recipient may be a user_id (int string) or @username
    chat_id: Any = recipient.lstrip("@") if recipient.startswith("@") else recipient
    try:
        chat_id = int(chat_id)
    except ValueError:
        pass  # leave as string @username for Telegram to resolve
    await bot.send_message(chat_id=chat_id, text=f"📄 Draft forwarded from LexAgent:\n\n{draft[:3000]}")


async def send_docusign(state: dict, recipient: str, cfg: "LexConfig") -> str:
    """Send a DocuSign signing request for the drafted contract."""
    raise NotImplementedError(
        "DocuSign integration is not yet wired. "
        "Add DOCUSIGN_API_KEY to .env and configure the DocuSign MCP server."
    )
