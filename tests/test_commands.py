import unittest

from slack_bot import blocks
from slack_bot.commands import HELP_TEXT, UNKNOWN_USER_MESSAGE, handle_slash_command
from slack_bot.fake_slack_client import FakeSlackClient
from slack_bot.planner_adapter import MockPlannerAdapter


def _payload(text: str, *, user_id: str = "U_SIMON", channel_id: str = "C123", trigger_id: str = "T123") -> dict:
    return {"text": text, "user_id": user_id, "channel_id": channel_id, "trigger_id": trigger_id}


class HandleSlashCommandTests(unittest.TestCase):
    def setUp(self):
        self.slack = FakeSlackClient()
        self.adapter = MockPlannerAdapter()

    def test_ping_bypasses_identity_mapping(self):
        # Even an unrecognized Slack user can ping -- it's the pre-identity
        # smoke test for "is signature verification even working" (3.6 step 1).
        resp = handle_slash_command(_payload("ping", user_id="U_TOTALLY_UNKNOWN"), self.slack, self.adapter)
        self.assertEqual(resp, {"response_type": "ephemeral", "text": "pong"})

    def test_whoami_reports_mapped_identity(self):
        resp = handle_slash_command(_payload("whoami"), self.slack, self.adapter)
        self.assertEqual(resp["text"], "simonn@emtech.us · admin")

    def test_unrecognized_email_is_refused_politely(self):
        resp = handle_slash_command(_payload("whoami", user_id="U_NOT_ON_ALLOWLIST"), self.slack, self.adapter)
        self.assertEqual(resp["text"], UNKNOWN_USER_MESSAGE)

    def test_status_reports_seeded_pipeline(self):
        resp = handle_slash_command(_payload("status"), self.slack, self.adapter)
        # MockPlannerAdapter seeds zero quotes -- everything should read 0.
        self.assertIn("won 0", resp["text"])
        self.assertIn("drafts 0", resp["text"])

    def test_plan_opens_a_modal_for_a_known_user(self):
        resp = handle_slash_command(_payload("plan"), self.slack, self.adapter)
        self.assertEqual(resp, {})
        self.assertEqual(len(self.slack.opened_views), 1)
        self.assertEqual(self.slack.opened_views[0]["callback_id"], blocks.PLAN_CALLBACK_ID)

    def test_plan_refuses_unrecognized_user_without_opening_a_modal(self):
        resp = handle_slash_command(_payload("plan", user_id="U_GUEST"), self.slack, self.adapter)
        self.assertEqual(resp["text"], UNKNOWN_USER_MESSAGE)
        self.assertEqual(self.slack.opened_views, [])

    def test_quote_opens_a_modal_when_a_planning_stage_plan_exists(self):
        # MockPlannerAdapter seeds "Vulcan Q4 Support" in status: planning.
        resp = handle_slash_command(_payload("quote"), self.slack, self.adapter)
        self.assertEqual(resp, {})
        self.assertEqual(len(self.slack.opened_views), 1)
        self.assertEqual(self.slack.opened_views[0]["callback_id"], blocks.QUOTE_CALLBACK_ID)

    def test_quote_tells_user_to_create_a_plan_first_when_none_exist(self):
        empty_adapter = MockPlannerAdapter()
        empty_adapter._projects.clear()  # no plans in "planning" status
        resp = handle_slash_command(_payload("quote"), self.slack, empty_adapter)
        self.assertIn("create one with", resp["text"])
        self.assertEqual(self.slack.opened_views, [])

    def test_unknown_subcommand_shows_help(self):
        resp = handle_slash_command(_payload("frobnicate"), self.slack, self.adapter)
        self.assertEqual(resp["text"], HELP_TEXT)

    def test_blank_text_shows_help(self):
        resp = handle_slash_command(_payload(""), self.slack, self.adapter)
        self.assertEqual(resp["text"], HELP_TEXT)


if __name__ == "__main__":
    unittest.main()
