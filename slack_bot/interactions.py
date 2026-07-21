"""Handles POST /slack/interactions payloads: view_submission (modal submits)
and block_actions (button clicks). Handbook 3.4-3.5.
"""

import json
import logging
import threading

from . import blocks, math_utils
from .approvals import notify_approvers
from .identity import resolve_identity
from .planner_adapter import TransitionNotAllowed, can_act_on_transition

logger = logging.getLogger("slack_bot.interactions")


def _run_in_background(fn, *args, **kwargs) -> None:
    """Handbook 3.4 #1: ack Slack within 3s, then do the real work. Fire-and-forget
    is fine here -- every downstream call logs its own failures, and there's no
    result channel back to the HTTP response that already returned.
    """
    threading.Thread(target=_safe_call, args=(fn, args, kwargs), daemon=True).start()


def _safe_call(fn, args, kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:
        logger.exception("background task %s failed", fn.__name__)


def dispatch_interaction(payload: dict, slack, adapter) -> dict:
    interaction_type = payload.get("type")
    if interaction_type == "view_submission":
        return handle_view_submission(payload, slack, adapter)
    if interaction_type == "block_actions":
        return handle_block_actions(payload, slack, adapter)
    logger.info("ignoring unhandled interaction type: %s", interaction_type)
    return {}


# -- view_submission ----------------------------------------------------------

def handle_view_submission(payload: dict, slack, adapter) -> dict:
    view = payload["view"]
    callback_id = view.get("callback_id")
    if callback_id == blocks.PLAN_CALLBACK_ID:
        return _submit_plan(view, slack, adapter)
    if callback_id == blocks.QUOTE_CALLBACK_ID:
        return _submit_quote(view, slack, adapter)
    if callback_id == blocks.REJECT_CALLBACK_ID:
        return _submit_reject(view, slack, adapter)
    logger.warning("unhandled view_submission callback_id: %s", callback_id)
    return {}


def _value(values: dict, block_id: str, action_id: str):
    return values[block_id][action_id]


def _optional_value(values: dict, block_id: str, action_id: str):
    return (values.get(block_id) or {}).get(action_id)


def _submit_plan(view: dict, slack, adapter) -> dict:
    metadata = json.loads(view["private_metadata"])
    values = view["state"]["values"]

    name = _value(values, "name_block", "name_input")["value"] or ""
    location = _value(values, "location_block", "location_input")["value"] or ""
    capex_opex = _value(values, "capex_opex_block", "capex_opex_input")["selected_option"]["value"]
    start_date = _value(values, "start_date_block", "start_date_input")["selected_date"]
    end_date = _value(values, "end_date_block", "end_date_input")["selected_date"]
    tier_raw = _value(values, "tier_block", "tier_input")["selected_option"]["value"]
    qty_raw = _value(values, "qty_block", "qty_input")["value"] or ""
    role = _value(values, "role_block", "role_input")["value"] or ""
    night_shift = bool(_value(values, "night_shift_block", "night_shift_input")["selected_options"])
    notes = (_value(values, "notes_block", "notes_input") or {}).get("value") or ""

    # Day-scheduling (2026-07-21, docs/decisions/0004-day-based-plan-scheduling.md):
    # "Schedule by" picks whether the week-range field or the day-picker
    # checkboxes are authoritative for this technician line. Only the field
    # matching the selected mode is parsed/validated -- the other is ignored.
    schedule_mode = _value(values, "schedule_mode_block", "schedule_mode_input")["selected_option"]["value"]
    weeks_raw = (_optional_value(values, "weeks_block", "weeks_input") or {}).get("value") or ""
    days_field = _optional_value(values, "days_block", "days_input") or {}
    selected_days = [opt["value"] for opt in days_field.get("selected_options", [])]

    errors = {}
    if not name.strip():
        errors["name_block"] = "Required."

    qty = None
    try:
        qty = int(qty_raw)
        if qty < 1:
            errors["qty_block"] = "Must be at least 1."
    except ValueError:
        errors["qty_block"] = "Must be a whole number."

    active_weeks = []
    active_days = []
    if schedule_mode == "day":
        active_days = selected_days
        if not active_days:
            errors["days_block"] = "Select at least one day."
    else:
        try:
            active_weeks = math_utils.parse_week_range(weeks_raw)
            if not active_weeks:
                errors["weeks_block"] = "Enter at least one week, e.g. 1-10."
        except ValueError:
            errors["weeks_block"] = "Use a format like 1-10 or 1-4,7-9."

    if errors:
        return {"response_action": "errors", "errors": errors}

    technician = {
        "id": "t1",
        "tier": int(tier_raw),
        "quantity": qty,
        "role": role,
        "nightShift": night_shift,
        # scheduleUnit lives on the technician line, not the project body --
        # this mirrors MockPlannerAdapter's seed data shape, where scheduling
        # info (activeWeeks today, activeDays now) is per-technician.
        "scheduleUnit": schedule_mode,
    }
    if schedule_mode == "day":
        technician["activeDays"] = active_days
    else:
        technician["activeWeeks"] = active_weeks

    project_body = {
        "name": name,
        "status": "planning",
        "location": location,
        "capexOpex": capex_opex,
        "startDate": start_date,
        "endDate": end_date,
        "notes": (notes + "\n\n(created from Slack)").strip(),
        "technicians": [technician],
    }
    _run_in_background(_create_plan_and_confirm, project_body, metadata, slack, adapter)
    return {}


def _create_plan_and_confirm(project_body: dict, metadata: dict, slack, adapter) -> None:
    actor_email = metadata["actor_email"]
    result = adapter.create_project(project_body, actor_email)
    logger.info("plan %s created by %s via Slack", result["id"], actor_email)

    text = (
        f":white_check_mark: Created plan *{project_body['name']}* ({result['id']}).\n"
        "Add more technician lines in the app: https://emblaze.emtech.us/planning"
    )
    slack.post_message(metadata["channel_id"], text=text)


def _submit_quote(view: dict, slack, adapter) -> dict:
    metadata = json.loads(view["private_metadata"])
    values = view["state"]["values"]

    plan_id = _value(values, "plan_block", "plan_input")["selected_option"]["value"]
    client_id = _value(values, "client_block", "client_input")["selected_option"]["value"]
    mgmt_raw = _value(values, "mgmt_block", "mgmt_input")["value"] or ""
    supp_raw = _value(values, "supp_block", "supp_input")["value"] or ""
    submit_now = bool(_value(values, "submit_now_block", "submit_now_input")["selected_options"])

    errors = {}
    if plan_id == "__none__":
        errors["plan_block"] = "No plan selected."
    if client_id == "__none__":
        errors["client_block"] = "No client selected."

    mgmt_pct = supp_pct = 0.0
    try:
        mgmt_pct = float(mgmt_raw)
    except ValueError:
        errors["mgmt_block"] = "Must be a number."
    try:
        supp_pct = float(supp_raw)
    except ValueError:
        errors["supp_block"] = "Must be a number."

    if errors:
        return {"response_action": "errors", "errors": errors}

    _run_in_background(
        _create_quote_and_confirm, plan_id, client_id, mgmt_pct, supp_pct, submit_now, metadata, slack, adapter
    )
    return {}


def _create_quote_and_confirm(plan_id, client_id, mgmt_pct, supp_pct, submit_now, metadata, slack, adapter) -> None:
    actor_email = metadata["actor_email"]

    project = adapter.get_project(plan_id)
    client = adapter.get_client(client_id)
    quote_number = adapter.allocate_quote_number()

    quote_body = {
        "name": project["body"]["name"],
        "quoteNumber": quote_number,
        "client": client["body"]["name"],
        "status": "draft",
        "approvalStatus": "draft",
        "mgmtFeePercent": mgmt_pct,
        "suppFeePercent": supp_pct,
        "projectIds": [plan_id],
        "travelItems": [],
        "electricalItems": [],
        "toolsItems": [],
        "incidentalsItems": [],
        "createdBy": actor_email,
    }
    result = adapter.create_quote(quote_body, actor_email)
    quote_id = result["id"]
    logger.info("quote %s (#%s) created by %s via Slack", quote_id, quote_number, actor_email)

    # Mirror the app's "Generate quote" behavior (handbook 2.5 worked example):
    # the plan moves planning -> quoting once it's attached to a quote.
    updated_project_body = dict(project["body"])
    updated_project_body["status"] = "quoting"
    updated_project_body["quoteId"] = quote_id
    updated_project_body["quoteName"] = quote_body["name"]
    adapter.update_project(plan_id, updated_project_body, project["ver"], actor_email)

    tier_rates = adapter.get_tier_weekly_rates()
    totals = math_utils.quote_totals(
        tier_rates, [project["body"]], mgmt_fee_percent=mgmt_pct, supp_fee_percent=supp_pct
    )

    text = (
        f":page_facing_up: Created quote #{quote_number} — *{quote_body['name']}* for {quote_body['client']}.\n"
        f"Grand total: *${totals['grandTotal']:,.0f}*"
    )

    if submit_now:
        adapter.transition_quote(quote_id, "pending_l1", result["ver"], actor_email)
        text += "\nSubmitted for approval."
        slack.post_message(metadata["channel_id"], text=text)
        notify_approvers(quote_id, slack, adapter)
    else:
        text += "\nLeft as a draft -- submit it from the app when you're ready."
        slack.post_message(metadata["channel_id"], text=text)


def _submit_reject(view: dict, slack, adapter) -> dict:
    metadata = json.loads(view["private_metadata"])
    values = view["state"]["values"]
    note = _value(values, "note_block", "note_input")["value"]

    if not note or not note.strip():
        return {"response_action": "errors", "errors": {"note_block": "A reason is required."}}

    _run_in_background(_reject_quote_and_update, metadata, note, slack, adapter)
    return {}


def _reject_quote_and_update(metadata: dict, note: str, slack, adapter) -> None:
    quote_id = metadata["quoteId"]
    ver = metadata["ver"]
    actor_email = metadata["actor_email"]
    channel = metadata["channel"]
    ts = metadata["ts"]

    quote = adapter.get_quote(quote_id)

    try:
        adapter.transition_quote(quote_id, "rejected", ver, actor_email, note=note)
    except TransitionNotAllowed:
        slack.post_message(channel, text=f"<@{metadata['slack_user_id']}> is not allowed to reject this quote.")
        return
    except ValueError:
        slack.post_message(channel, text="Someone already acted on this quote -- refresh and check the app.")
        return

    body = quote["body"]
    text = f":x: Quote #{body.get('quoteNumber')} — {body.get('name')} rejected by {actor_email}.\nReason: {note}"
    slack.update_message(channel, ts, text=text, blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}])
    logger.info("quote %s rejected by %s", quote_id, actor_email)


# -- block_actions --------------------------------------------------------

def handle_block_actions(payload: dict, slack, adapter) -> dict:
    action = payload["actions"][0]
    action_id = action["action_id"]

    if action_id == "quote_open_in_app":
        return {}  # `url` button -- Slack opens the link client-side, nothing for us to do

    slack_user_id = payload["user"]["id"]
    identity = resolve_identity(slack_user_id, slack, adapter)

    if identity is None:
        slack.post_to_response_url(
            payload["response_url"],
            {"response_type": "ephemeral", "text": "I don't recognize your email in Emblaze's user list."},
        )
        return {}

    if action_id == "quote_approve":
        return _handle_approve(action, identity, payload, slack, adapter)
    if action_id == "quote_reject":
        return _handle_reject_click(action, identity, payload, slack, adapter)

    logger.warning("unhandled block action: %s", action_id)
    return {}


def _handle_approve(action: dict, identity: dict, payload: dict, slack, adapter) -> dict:
    value = json.loads(action["value"])
    quote_id, ver = value["quoteId"], value["ver"]
    channel = payload["channel"]["id"]
    ts = payload["message"]["ts"]

    _run_in_background(_approve_quote_and_update, quote_id, ver, identity, channel, ts, slack, adapter)
    return {}


def _approve_quote_and_update(quote_id, ver, identity, channel, ts, slack, adapter) -> None:
    quote = adapter.get_quote(quote_id)
    from_status = quote["body"].get("approvalStatus", "draft")
    to_status = {"pending_l1": "pending_l2", "pending_l2": "final_approved"}.get(from_status)

    if to_status is None:
        slack.update_message(channel, ts, text=f"This quote is already `{from_status}` -- nothing to approve.")
        return

    if not can_act_on_transition(identity["role"], from_status, to_status):
        slack.post_message(channel, text=f"{identity['email']} ({identity['role']}) can't approve this stage.")
        return

    try:
        adapter.transition_quote(quote_id, to_status, ver, identity["email"])
    except ValueError:
        slack.update_message(channel, ts, text="Someone already acted on this quote -- refresh and check the app.")
        return
    except TransitionNotAllowed:
        slack.update_message(channel, ts, text=f"{identity['email']} ({identity['role']}) can't approve this stage.")
        return

    body = quote["body"]
    text = (
        f":white_check_mark: Quote #{body.get('quoteNumber')} — {body.get('name')} approved by "
        f"{identity['email']} (now `{to_status}`)."
    )
    slack.update_message(channel, ts, text=text, blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}])

    if to_status == "pending_l2":
        notify_approvers(quote_id, slack, adapter)


def _handle_reject_click(action: dict, identity: dict, payload: dict, slack, adapter) -> dict:
    value = json.loads(action["value"])
    quote_id, ver = value["quoteId"], value["ver"]

    quote = adapter.get_quote(quote_id)
    from_status = quote["body"].get("approvalStatus", "draft")

    if not can_act_on_transition(identity["role"], from_status, "rejected"):
        slack.post_to_response_url(
            payload["response_url"],
            {"response_type": "ephemeral", "text": f"{identity['email']} ({identity['role']}) can't reject this stage."},
        )
        return {}

    metadata = {
        "quoteId": quote_id,
        "ver": ver,
        "channel": payload["channel"]["id"],
        "ts": payload["message"]["ts"],
        "actor_email": identity["email"],
        "slack_user_id": payload["user"]["id"],
    }
    view = blocks.reject_modal(private_metadata=metadata)
    slack.open_view(payload["trigger_id"], view)
    return {}
