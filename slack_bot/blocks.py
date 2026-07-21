"""Block Kit builders for the three modals and two messages Part 3 describes (3.5).

Design these visually at https://app.slack.com/block-kit-builder if you need to
change them -- paste the resulting JSON back in here.
"""

from __future__ import annotations

import json

PLAN_CALLBACK_ID = "emblaze_plan_submit"
QUOTE_CALLBACK_ID = "emblaze_quote_submit"
REJECT_CALLBACK_ID = "emblaze_reject_submit"

# Day-scheduling (2026-07-21, docs/decisions/0004-day-based-plan-scheduling.md):
# the plan modal's per-technician day-picker offers these seven days. Values are
# lowercase 3-letter weekday abbreviations -- this is the exact shape written to
# a technician's `activeDays` list in interactions.py. Order here is also the
# display order in the modal.
DAY_OPTIONS = [
    ("Mon", "mon"),
    ("Tue", "tue"),
    ("Wed", "wed"),
    ("Thu", "thu"),
    ("Fri", "fri"),
    ("Sat", "sat"),
    ("Sun", "sun"),
]


def _plain_text(text: str, emoji: bool = True) -> dict:
    return {"type": "plain_text", "text": text, "emoji": emoji}


def _input(block_id: str, label: str, element: dict, *, optional: bool = False) -> dict:
    return {
        "type": "input",
        "block_id": block_id,
        "label": _plain_text(label),
        "element": element,
        "optional": optional,
    }


def _text_input(action_id: str, *, initial_value: str | None = None, multiline: bool = False, placeholder: str | None = None) -> dict:
    el = {"type": "plain_text_input", "action_id": action_id, "multiline": multiline}
    if initial_value is not None:
        el["initial_value"] = initial_value
    if placeholder is not None:
        el["placeholder"] = _plain_text(placeholder)
    return el


def _static_select(action_id: str, options: list, *, initial_option=None) -> dict:
    el = {
        "type": "static_select",
        "action_id": action_id,
        "options": options,
        "placeholder": _plain_text("Select…"),
    }
    if initial_option is not None:
        el["initial_option"] = initial_option
    return el


def _option(label: str, value: str) -> dict:
    return {"text": _plain_text(label), "value": value}


def _checkbox(action_id: str, label: str, value: str = "true") -> dict:
    return {
        "type": "checkboxes",
        "action_id": action_id,
        "options": [{"text": _plain_text(label), "value": value}],
    }


def _checkboxes(action_id: str, options: list) -> dict:
    """Multi-option checkboxes, e.g. the day-picker's Mon-Sun list."""
    return {
        "type": "checkboxes",
        "action_id": action_id,
        "options": [_option(label, value) for label, value in options],
    }


def plan_modal(tier_weekly_rates: dict, *, private_metadata: dict) -> dict:
    tier_options = [
        _option(f"T{tier} — ${rate:,}/wk", str(tier))
        for tier, rate in sorted(tier_weekly_rates.items(), reverse=True)
    ]

    return {
        "type": "modal",
        "callback_id": PLAN_CALLBACK_ID,
        "private_metadata": json.dumps(private_metadata),
        "title": _plain_text("New plan"),
        "submit": _plain_text("Create plan"),
        "close": _plain_text("Cancel"),
        "blocks": [
            _input("name_block", "Name", _text_input("name_input")),
            _input("location_block", "Location", _text_input("location_input")),
            _input(
                "capex_opex_block",
                "CAPEX / OPEX",
                _static_select("capex_opex_input", [_option("CAPEX", "CAPEX"), _option("OPEX", "OPEX")]),
            ),
            _input(
                "start_date_block",
                "Start date",
                {"type": "datepicker", "action_id": "start_date_input", "placeholder": _plain_text("Select a date")},
            ),
            _input(
                "end_date_block",
                "End date",
                {"type": "datepicker", "action_id": "end_date_input", "placeholder": _plain_text("Select a date")},
            ),
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Technician line* (add more in the app afterwards)"}},
            _input("tier_block", "Tier", _static_select("tier_input", tier_options)),
            _input("qty_block", "Qty", _text_input("qty_input", placeholder="e.g. 2")),
            _input("role_block", "Role", _text_input("role_input", placeholder="e.g. install crew")),
            _input(
                "night_shift_block",
                "Night shift",
                _checkbox("night_shift_input", "Night shift (+$400/wk per tech)"),
                optional=True,
            ),
            # Day-scheduling (0004): "Schedule by" picks which of the two fields
            # below is authoritative. interactions.py validates only the field
            # matching the selected mode -- the other is ignored, not required.
            _input(
                "schedule_mode_block",
                "Schedule by",
                _static_select(
                    "schedule_mode_input",
                    [_option("Week range", "week"), _option("Specific days", "day")],
                    initial_option=_option("Week range", "week"),
                ),
            ),
            _input(
                "weeks_block",
                "Weeks (used when scheduling by week)",
                _text_input("weeks_input", placeholder="1-10 or 1-4,7-9"),
                optional=True,
            ),
            _input(
                "days_block",
                "Days (used when scheduling by day)",
                _checkboxes("days_input", DAY_OPTIONS),
                optional=True,
            ),
            _input("notes_block", "Notes", _text_input("notes_input", multiline=True), optional=True),
        ],
    }


def quote_modal(projects: list, clients: list, *, private_metadata: dict) -> dict:
    project_options = [_option(p["body"]["name"], p["id"]) for p in projects] or [
        _option("No plans in 'planning' status", "__none__")
    ]
    client_options = [_option(c["body"]["name"], c["id"]) for c in clients] or [
        _option("No clients configured", "__none__")
    ]

    return {
        "type": "modal",
        "callback_id": QUOTE_CALLBACK_ID,
        "private_metadata": json.dumps(private_metadata),
        "title": _plain_text("New quote"),
        "submit": _plain_text("Create quote"),
        "close": _plain_text("Cancel"),
        "blocks": [
            _input("plan_block", "Plan", _static_select("plan_input", project_options)),
            _input("client_block", "Client", _static_select("client_input", client_options)),
            _input("mgmt_block", "Management %", _text_input("mgmt_input", initial_value="10")),
            _input("supp_block", "Supplemental %", _text_input("supp_input", initial_value="8")),
            _input(
                "submit_now_block",
                "Submit for approval immediately?",
                _checkbox("submit_now_input", "Yes, submit now"),
                optional=True,
            ),
        ],
    }


def reject_modal(*, private_metadata: dict) -> dict:
    return {
        "type": "modal",
        "callback_id": REJECT_CALLBACK_ID,
        "private_metadata": json.dumps(private_metadata),
        "title": _plain_text("Reject quote"),
        "submit": _plain_text("Reject"),
        "close": _plain_text("Cancel"),
        "blocks": [
            _input(
                "note_block",
                "Reason (goes back to the creator)",
                _text_input("note_input", multiline=True, placeholder="Why is this being rejected?"),
            ),
        ],
    }


def approval_dm_blocks(*, quote_id: str, ver: int, quote_number: int, name: str, client: str, grand_total: float, submitted_by: str, stage: str, show_buttons: bool) -> list:
    header = f"*Quote #{quote_number} — {name}*"
    details = (
        f"Client: *{client}*\n"
        f"Grand total: *${grand_total:,.0f}*\n"
        f"Submitted by: {submitted_by}\n"
        f"Stage: `{stage}`"
    )
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{header}\n{details}"}},
    ]

    action_value = json.dumps({"quoteId": quote_id, "ver": ver})
    elements = []
    if show_buttons:
        elements.append(
            {
                "type": "button",
                "text": _plain_text("✅ Approve"),
                "style": "primary",
                "action_id": "quote_approve",
                "value": action_value,
                "confirm": {
                    "title": _plain_text("Approve this quote?"),
                    "text": _plain_text(f"Quote #{quote_number} — {name}"),
                    "confirm": _plain_text("Approve"),
                    "deny": _plain_text("Cancel"),
                },
            }
        )
        elements.append(
            {
                "type": "button",
                "text": _plain_text("❌ Reject"),
                "style": "danger",
                "action_id": "quote_reject",
                "value": action_value,
            }
        )
    elements.append(
        {
            "type": "button",
            "text": _plain_text("Open in Emblaze"),
            "url": "https://emblaze.emtech.us/quotes",
            "action_id": "quote_open_in_app",
        }
    )
    blocks.append({"type": "actions", "elements": elements})
    return blocks


STATUS_EMOJI = {
    "won": "🟢",
    "final_review": "🟠",
    "pending": "🟡",
    "draft": "⚪",
    "rejected": "🔴",
}


def status_message_text(counts: dict, waiting_lines: list) -> str:
    lines = [
        f"{STATUS_EMOJI['won']} won {counts.get('won', 0)}",
        f"{STATUS_EMOJI['final_review']} final review {counts.get('final_review', 0)}",
        f"{STATUS_EMOJI['pending']} pending {counts.get('pending', 0)}",
        f"{STATUS_EMOJI['draft']} drafts {counts.get('draft', 0)}",
        f"{STATUS_EMOJI['rejected']} rejected {counts.get('rejected', 0)}",
    ]
    text = " · ".join(lines)
    for waiting_line in waiting_lines:
        text += f"\n{STATUS_EMOJI['pending']} {waiting_line}"
    return text
