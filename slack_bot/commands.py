"""Slash command dispatch: /emblaze <ping|whoami|status|plan|quote>  (handbook 3.1, 3.6)."""

import logging

from . import blocks
from .identity import resolve_identity

logger = logging.getLogger("slack_bot.commands")

UNKNOWN_USER_MESSAGE = (
    "I don't recognize your email in Emblaze's user list. Ask an admin to add you in Settings, then try again."
)

HELP_TEXT = (
    "*Emblaze bot commands*\n"
    "`/emblaze ping` — health check\n"
    "`/emblaze whoami` — your mapped Emblaze identity\n"
    "`/emblaze status` — pipeline summary\n"
    "`/emblaze plan` — open the new-plan form\n"
    "`/emblaze quote` — open the new-quote form"
)


def _ephemeral(text: str) -> dict:
    return {"response_type": "ephemeral", "text": text}


def handle_slash_command(payload: dict, slack, adapter) -> dict:
    """payload: parsed form fields from POST /slack/commands.

    Returns the dict to send back as the immediate (<3s) HTTP response body.
    Step 1 (guardrail 3.7 / signature verification) already happened in routes.py
    before this function is ever called.
    """
    text = (payload.get("text") or "").strip()
    sub = text.split(None, 1)[0].lower() if text else "help"
    slack_user_id = payload["user_id"]

    # ping intentionally skips identity mapping -- it's the smoke test for "is
    # signature verification even working", per build-order step 1 (3.6).
    if sub == "ping":
        return _ephemeral("pong")

    identity = resolve_identity(slack_user_id, slack, adapter)
    if identity is None:
        return _ephemeral(UNKNOWN_USER_MESSAGE)

    if sub == "whoami":
        return _ephemeral(f"{identity['email']} · {identity['role']}")

    if sub == "status":
        return _ephemeral(_build_status_text(adapter))

    if sub == "plan":
        return _open_plan_modal(payload, slack, adapter, identity)

    if sub == "quote":
        return _open_quote_modal(payload, slack, adapter, identity)

    return _ephemeral(HELP_TEXT)


def _build_status_text(adapter) -> str:
    quotes = adapter.list_quotes()
    counts = {"won": 0, "final_review": 0, "pending": 0, "draft": 0, "rejected": 0}
    waiting_lines = []

    for q in quotes:
        status = q["body"].get("approvalStatus", "draft")
        number = q["body"].get("quoteNumber")
        name = q["body"].get("name", "?")

        if status == "approved":
            counts["won"] += 1
        elif status in ("final_approved", "sent"):
            counts["final_review"] += 1
        elif status in ("pending_l1", "pending_l2"):
            counts["pending"] += 1
            waiting_on = "L1" if status == "pending_l1" else "L2"
            waiting_lines.append(f"#{number} {name}… ⏳ waiting on {waiting_on}")
        elif status == "rejected":
            counts["rejected"] += 1
        else:
            counts["draft"] += 1

    return blocks.status_message_text(counts, waiting_lines)


def _open_plan_modal(payload: dict, slack, adapter, identity: dict) -> dict:
    private_metadata = {"channel_id": payload["channel_id"], "actor_email": identity["email"]}
    view = blocks.plan_modal(adapter.get_tier_weekly_rates(), private_metadata=private_metadata)
    slack.open_view(payload["trigger_id"], view)
    return {}


def _open_quote_modal(payload: dict, slack, adapter, identity: dict) -> dict:
    projects = adapter.list_projects(status="planning")
    teams = adapter.list_teams()
    if not projects:
        return _ephemeral("No plans in 'planning' status yet — create one with `/emblaze plan` first.")
    private_metadata = {"channel_id": payload["channel_id"], "actor_email": identity["email"]}
    view = blocks.quote_modal(projects, teams, private_metadata=private_metadata)
    slack.open_view(payload["trigger_id"], view)
    return {}
