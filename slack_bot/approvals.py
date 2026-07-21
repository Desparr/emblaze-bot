"""Sends the approval DM described in handbook 3.5 whenever a quote enters a
pending stage. Called from both this bot's own transitions (quote submitted
from `/emblaze quote`, or approved from pending_l1 -> pending_l2) and -- once
merged into the real repo -- should also be wired as a callback from
planner_api.py's transition endpoint itself, so approvals started from the
app's bell icon also reach Slack, not only ones the bot initiated.
"""

import logging

from . import blocks
from .planner_adapter import role_meets

logger = logging.getLogger("slack_bot.approvals")

STAGE_REQUIRED_ROLE = {
    "pending_l1": "approver_l1",
    "pending_l2": "approver_l2",
}


def eligible_approver_emails(stage: str, users: dict) -> list:
    required_role = STAGE_REQUIRED_ROLE.get(stage)
    if required_role is None:
        return []
    return [email for email, record in users.items() if role_meets(record["role"], required_role)]


def notify_approvers(quote_id: str, slack, adapter) -> None:
    quote = adapter.get_quote(quote_id)
    body = quote["body"]
    stage = body.get("approvalStatus", "draft")

    if stage not in STAGE_REQUIRED_ROLE:
        return

    users = adapter.get_users()
    recipients = eligible_approver_emails(stage, users)
    if not recipients:
        logger.warning("no approvers found for stage %s (quote %s)", stage, quote_id)
        return

    tier_rates = adapter.get_tier_weekly_rates()
    projects = [adapter.get_project(pid)["body"] for pid in body.get("projectIds", [])]

    from . import math_utils

    totals = math_utils.quote_totals(
        tier_rates,
        projects,
        mgmt_fee_percent=body.get("mgmtFeePercent", 0),
        supp_fee_percent=body.get("suppFeePercent", 0),
        travel_items=body.get("travelItems"),
        electrical_items=body.get("electricalItems"),
        tools_items=body.get("toolsItems"),
        incidentals_items=body.get("incidentalsItems"),
    )

    dm_blocks = blocks.approval_dm_blocks(
        quote_id=quote_id,
        ver=quote["ver"],
        quote_number=body.get("quoteNumber"),
        name=body.get("name", "?"),
        team=body.get("team", "?"),
        grand_total=totals["grandTotal"],
        submitted_by=body.get("createdBy", "?"),
        stage=stage,
        show_buttons=True,
    )

    for email in recipients:
        slack_user_id = slack.lookup_user_id_by_email(email)
        if not slack_user_id:
            logger.warning("approver %s has no matching Slack account", email)
            continue
        slack.post_message(
            slack_user_id,
            text=f"Quote #{body.get('quoteNumber')} — {body.get('name')} needs your approval",
            blocks=dm_blocks,
        )
