import json
import unittest
from unittest import mock

from slack_bot import blocks, interactions
from slack_bot.fake_slack_client import FakeSlackClient
from slack_bot.planner_adapter import MockPlannerAdapter


def _run_sync(fn, *args, **kwargs) -> None:
    """Replacement for interactions._run_in_background that runs inline, so
    tests don't have to sleep-and-poll for a daemon thread to finish."""
    fn(*args, **kwargs)


def _view_submission(callback_id: str, values: dict, private_metadata: dict) -> dict:
    return {
        "type": "view_submission",
        "view": {
            "callback_id": callback_id,
            "private_metadata": json.dumps(private_metadata),
            "state": {"values": values},
        },
    }


def _text_value(v):
    return {"value": v}


def _select_value(v):
    return {"selected_option": {"value": v}}


def _checkbox_value(checked: bool):
    return {"selected_options": (["x"] if checked else [])}


def _day_checkboxes_value(days: list) -> dict:
    return {"selected_options": [{"value": d} for d in days]}


def _block_actions(action_id: str, value: dict, *, user_id="U_PRIYA", channel="C1", ts="123.456", trigger_id="T1"):
    return {
        "type": "block_actions",
        "user": {"id": user_id},
        "actions": [{"action_id": action_id, "value": json.dumps(value)}],
        "channel": {"id": channel},
        "message": {"ts": ts},
        "response_url": "https://hooks.slack.test/response",
        "trigger_id": trigger_id,
    }


# Week-mode is the default schedule_mode -- these values exercise the plan
# modal exactly as it behaved pre-day-scheduling, plus the new (always-present)
# schedule_mode_block defaulted to "week" and an empty days_block.
PLAN_VALUES = {
    "name_block": {"name_input": _text_value("Test Plan")},
    "location_block": {"location_input": _text_value("GEG1 - Spokane")},
    "capex_opex_block": {"capex_opex_input": _select_value("OPEX")},
    "start_date_block": {"start_date_input": {"selected_date": "2026-08-01"}},
    "end_date_block": {"end_date_input": {"selected_date": "2026-09-01"}},
    "tier_block": {"tier_input": _select_value("3")},
    "qty_block": {"qty_input": _text_value("2")},
    "role_block": {"role_input": _text_value("install crew")},
    "night_shift_block": {"night_shift_input": _checkbox_value(False)},
    "schedule_mode_block": {"schedule_mode_input": _select_value("week")},
    "weeks_block": {"weeks_input": _text_value("1-4")},
    "days_block": {"days_input": _day_checkboxes_value([])},
    "notes_block": {"notes_input": _text_value("")},
}


class SubmitPlanTests(unittest.TestCase):
    def setUp(self):
        self.slack = FakeSlackClient()
        self.adapter = MockPlannerAdapter()
        patcher = mock.patch("slack_bot.interactions._run_in_background", side_effect=_run_sync)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_valid_submission_creates_project_and_confirms_in_channel(self):
        payload = _view_submission(
            blocks.PLAN_CALLBACK_ID, PLAN_VALUES, {"channel_id": "C1", "actor_email": "simonn@emtech.us"}
        )
        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp, {})

        projects = [p for p in self.adapter.list_projects() if p["body"]["name"] == "Test Plan"]
        self.assertEqual(len(projects), 1)
        tech = projects[0]["body"]["technicians"][0]
        self.assertEqual(tech["activeWeeks"], [1, 2, 3, 4])
        self.assertEqual(tech["scheduleUnit"], "week")
        self.assertNotIn("activeDays", tech)
        # scheduleUnit lives per-technician, not at the top of the project body.
        self.assertNotIn("scheduleUnit", projects[0]["body"])

        self.assertEqual(len(self.slack.sent_messages), 1)
        self.assertIn("Test Plan", self.slack.sent_messages[0]["text"])

    def test_missing_name_is_rejected_without_creating_a_project(self):
        values = dict(PLAN_VALUES)
        values["name_block"] = {"name_input": _text_value("")}
        payload = _view_submission(blocks.PLAN_CALLBACK_ID, values, {"channel_id": "C1", "actor_email": "simonn@emtech.us"})

        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp["response_action"], "errors")
        self.assertIn("name_block", resp["errors"])
        self.assertEqual(self.slack.sent_messages, [])

    def test_bad_week_range_is_rejected(self):
        values = dict(PLAN_VALUES)
        values["weeks_block"] = {"weeks_input": _text_value("not-a-range")}
        payload = _view_submission(blocks.PLAN_CALLBACK_ID, values, {"channel_id": "C1", "actor_email": "simonn@emtech.us"})

        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp["response_action"], "errors")
        self.assertIn("weeks_block", resp["errors"])

    def test_non_integer_quantity_is_rejected(self):
        values = dict(PLAN_VALUES)
        values["qty_block"] = {"qty_input": _text_value("two")}
        payload = _view_submission(blocks.PLAN_CALLBACK_ID, values, {"channel_id": "C1", "actor_email": "simonn@emtech.us"})

        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp["response_action"], "errors")
        self.assertIn("qty_block", resp["errors"])

    # -- day-scheduling (docs/decisions/0004-day-based-plan-scheduling.md) --

    def test_day_mode_submission_creates_project_with_active_days(self):
        values = dict(PLAN_VALUES)
        values["schedule_mode_block"] = {"schedule_mode_input": _select_value("day")}
        values["days_block"] = {"days_input": _day_checkboxes_value(["mon", "wed", "fri"])}
        payload = _view_submission(
            blocks.PLAN_CALLBACK_ID, values, {"channel_id": "C1", "actor_email": "simonn@emtech.us"}
        )

        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp, {})

        projects = [p for p in self.adapter.list_projects() if p["body"]["name"] == "Test Plan"]
        self.assertEqual(len(projects), 1)
        tech = projects[0]["body"]["technicians"][0]
        self.assertEqual(tech["scheduleUnit"], "day")
        self.assertEqual(tech["activeDays"], ["mon", "wed", "fri"])
        self.assertNotIn("activeWeeks", tech)

    def test_day_mode_without_selecting_any_day_is_rejected(self):
        values = dict(PLAN_VALUES)
        values["schedule_mode_block"] = {"schedule_mode_input": _select_value("day")}
        values["days_block"] = {"days_input": _day_checkboxes_value([])}
        payload = _view_submission(
            blocks.PLAN_CALLBACK_ID, values, {"channel_id": "C1", "actor_email": "simonn@emtech.us"}
        )

        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp["response_action"], "errors")
        self.assertIn("days_block", resp["errors"])
        self.assertEqual(self.adapter.list_projects(status="planning"), self.adapter.list_projects(status="planning"))
        self.assertEqual([p for p in self.adapter.list_projects() if p["body"]["name"] == "Test Plan"], [])

    def test_day_mode_ignores_an_invalid_week_range_since_weeks_block_is_not_the_active_mode(self):
        # When schedule_mode is "day", weeks_block is not validated at all --
        # even garbage in it should not block submission.
        values = dict(PLAN_VALUES)
        values["schedule_mode_block"] = {"schedule_mode_input": _select_value("day")}
        values["weeks_block"] = {"weeks_input": _text_value("not-a-range")}
        values["days_block"] = {"days_input": _day_checkboxes_value(["tue"])}
        payload = _view_submission(
            blocks.PLAN_CALLBACK_ID, values, {"channel_id": "C1", "actor_email": "simonn@emtech.us"}
        )

        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp, {})
        projects = [p for p in self.adapter.list_projects() if p["body"]["name"] == "Test Plan"]
        self.assertEqual(projects[0]["body"]["technicians"][0]["activeDays"], ["tue"])


QUOTE_VALUES_TEMPLATE = {
    "mgmt_block": {"mgmt_input": _text_value("10")},
    "supp_block": {"supp_input": _text_value("8")},
}


class SubmitQuoteTests(unittest.TestCase):
    def setUp(self):
        self.slack = FakeSlackClient()
        self.adapter = MockPlannerAdapter()
        patcher = mock.patch("slack_bot.interactions._run_in_background", side_effect=_run_sync)
        patcher.start()
        self.addCleanup(patcher.stop)
        # MockPlannerAdapter seeds exactly one planning-stage project + two clients.
        self.seed_project = self.adapter.list_projects(status="planning")[0]
        self.client_id = self.adapter.list_clients()[0]["id"]

    def _values(self, *, submit_now: bool):
        values = dict(QUOTE_VALUES_TEMPLATE)
        values["plan_block"] = {"plan_input": _select_value(self.seed_project["id"])}
        values["client_block"] = {"client_input": _select_value(self.client_id)}
        values["submit_now_block"] = {"submit_now_input": _checkbox_value(submit_now)}
        return values

    def test_draft_quote_does_not_transition_or_notify(self):
        payload = _view_submission(
            blocks.QUOTE_CALLBACK_ID, self._values(submit_now=False), {"channel_id": "C1", "actor_email": "alex@emtech.us"}
        )
        interactions.dispatch_interaction(payload, self.slack, self.adapter)

        quotes = self.adapter.list_quotes()
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["body"]["approvalStatus"], "draft")
        # No approval DMs for a draft.
        self.assertTrue(all("needs your approval" not in m["text"] for m in self.slack.sent_messages))
        # The plan should have flipped to "quoting" and gained quoteId/quoteName.
        updated_project = self.adapter.get_project(self.seed_project["id"])
        self.assertEqual(updated_project["body"]["status"], "quoting")

    def test_submit_now_transitions_to_pending_l1_and_notifies_eligible_approvers(self):
        payload = _view_submission(
            blocks.QUOTE_CALLBACK_ID, self._values(submit_now=True), {"channel_id": "C1", "actor_email": "alex@emtech.us"}
        )
        interactions.dispatch_interaction(payload, self.slack, self.adapter)

        quotes = self.adapter.list_quotes()
        self.assertEqual(quotes[0]["body"]["approvalStatus"], "pending_l1")

        # Seeded users eligible for pending_l1 (approver_l1+): simonn (admin),
        # priya (approver_l1), josh (approver_l2). alex (member) is not.
        # FakeSlackClient only has Slack IDs for simonn/josh/priya/alex, so all
        # three eligible+mapped approvers should have gotten a DM.
        dm_texts = [m["text"] for m in self.slack.sent_messages if "needs your approval" in m["text"]]
        self.assertEqual(len(dm_texts), 3)

    def test_missing_plan_selection_is_rejected(self):
        values = self._values(submit_now=False)
        values["plan_block"] = {"plan_input": _select_value("__none__")}
        payload = _view_submission(blocks.QUOTE_CALLBACK_ID, values, {"channel_id": "C1", "actor_email": "alex@emtech.us"})

        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp["response_action"], "errors")
        self.assertIn("plan_block", resp["errors"])

    def test_non_numeric_management_fee_is_rejected(self):
        values = self._values(submit_now=False)
        values["mgmt_block"] = {"mgmt_input": _text_value("ten percent")}
        payload = _view_submission(blocks.QUOTE_CALLBACK_ID, values, {"channel_id": "C1", "actor_email": "alex@emtech.us"})

        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp["response_action"], "errors")
        self.assertIn("mgmt_block", resp["errors"])


class ApproveRejectFlowTests(unittest.TestCase):
    def setUp(self):
        self.slack = FakeSlackClient()
        self.adapter = MockPlannerAdapter()
        patcher = mock.patch("slack_bot.interactions._run_in_background", side_effect=_run_sync)
        patcher.start()
        self.addCleanup(patcher.stop)

        quote = self.adapter.create_quote(
            {"name": "Test Quote", "quoteNumber": 42, "approvalStatus": "draft"}, "alex@emtech.us"
        )
        self.adapter.transition_quote(quote["id"], "pending_l1", quote["ver"], "alex@emtech.us")
        self.quote_id = quote["id"]
        self.ver = self.adapter.get_quote(self.quote_id)["ver"]

    def test_eligible_approver_advances_the_quote(self):
        payload = _block_actions("quote_approve", {"quoteId": self.quote_id, "ver": self.ver}, user_id="U_PRIYA")
        interactions.dispatch_interaction(payload, self.slack, self.adapter)

        self.assertEqual(self.adapter.get_quote(self.quote_id)["body"]["approvalStatus"], "pending_l2")

    def test_member_cannot_approve_and_quote_is_unchanged(self):
        payload = _block_actions("quote_approve", {"quoteId": self.quote_id, "ver": self.ver}, user_id="U_ALEX")
        interactions.dispatch_interaction(payload, self.slack, self.adapter)

        self.assertEqual(self.adapter.get_quote(self.quote_id)["body"]["approvalStatus"], "pending_l1")
        # Role-gate failure posts a fresh message rather than editing the DM.
        self.assertIn("can't approve", self.slack.sent_messages[-1]["text"])

    def test_stale_version_gets_a_friendly_message_not_a_stack_trace(self):
        # ver=999 will never match the adapter's real version -> ValueError inside
        # transition_quote, which _approve_quote_and_update must turn into a
        # plain-English message rather than leaking the raw exception text.
        payload = _block_actions("quote_approve", {"quoteId": self.quote_id, "ver": 999}, user_id="U_PRIYA")
        interactions.dispatch_interaction(payload, self.slack, self.adapter)

        self.assertEqual(self.adapter.get_quote(self.quote_id)["body"]["approvalStatus"], "pending_l1")
        last_message = self.slack.updated_messages[-1]["text"]
        self.assertNotIn("stale ver", last_message)  # no leaked internals
        self.assertIn("refresh", last_message)

    def test_unrecognized_slack_user_is_refused_via_response_url(self):
        payload = _block_actions("quote_approve", {"quoteId": self.quote_id, "ver": self.ver}, user_id="U_MYSTERY")
        interactions.dispatch_interaction(payload, self.slack, self.adapter)
        # Quote must be untouched -- no identity, no action.
        self.assertEqual(self.adapter.get_quote(self.quote_id)["body"]["approvalStatus"], "pending_l1")

    def test_reject_click_opens_a_modal_for_an_eligible_approver(self):
        payload = _block_actions("quote_reject", {"quoteId": self.quote_id, "ver": self.ver}, user_id="U_PRIYA")
        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)

        self.assertEqual(resp, {})
        self.assertEqual(len(self.slack.opened_views), 1)
        self.assertEqual(self.slack.opened_views[0]["callback_id"], blocks.REJECT_CALLBACK_ID)

    def test_reject_click_from_a_member_is_refused_without_opening_a_modal(self):
        payload = _block_actions("quote_reject", {"quoteId": self.quote_id, "ver": self.ver}, user_id="U_ALEX")
        interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(self.slack.opened_views, [])

    def test_reject_submission_without_a_note_is_rejected(self):
        metadata = {
            "quoteId": self.quote_id,
            "ver": self.ver,
            "channel": "C1",
            "ts": "123.456",
            "actor_email": "priya@emtech.us",
            "slack_user_id": "U_PRIYA",
        }
        payload = _view_submission(blocks.REJECT_CALLBACK_ID, {"note_block": {"note_input": _text_value("")}}, metadata)
        resp = interactions.dispatch_interaction(payload, self.slack, self.adapter)
        self.assertEqual(resp["response_action"], "errors")
        self.assertEqual(self.adapter.get_quote(self.quote_id)["body"]["approvalStatus"], "pending_l1")

    def test_reject_submission_with_a_note_rejects_the_quote(self):
        metadata = {
            "quoteId": self.quote_id,
            "ver": self.ver,
            "channel": "C1",
            "ts": "123.456",
            "actor_email": "priya@emtech.us",
            "slack_user_id": "U_PRIYA",
        }
        payload = _view_submission(
            blocks.REJECT_CALLBACK_ID, {"note_block": {"note_input": _text_value("Missing travel budget")}}, metadata
        )
        interactions.dispatch_interaction(payload, self.slack, self.adapter)

        quote = self.adapter.get_quote(self.quote_id)
        self.assertEqual(quote["body"]["approvalStatus"], "rejected")
        self.assertEqual(quote["body"]["statusLog"][-1]["note"], "Missing travel budget")


if __name__ == "__main__":
    unittest.main()
