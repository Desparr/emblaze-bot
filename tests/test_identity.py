import unittest

from slack_bot.fake_slack_client import FakeSlackClient
from slack_bot.identity import resolve_identity
from slack_bot.planner_adapter import MockPlannerAdapter


class ResolveIdentityTests(unittest.TestCase):
    def setUp(self):
        self.slack = FakeSlackClient()
        self.adapter = MockPlannerAdapter()

    def test_known_slack_user_resolves_to_allowlisted_role(self):
        identity = resolve_identity("U_SIMON", self.slack, self.adapter)
        self.assertEqual(identity["email"], "simonn@emtech.us")
        self.assertEqual(identity["role"], "admin")

    def test_desmond_resolves_to_allowlisted_role(self):
        identity = resolve_identity("U_DESMOND", self.slack, self.adapter)
        self.assertEqual(identity["email"], "desmondp@emtech.us")
        self.assertEqual(identity["role"], "admin")

    def test_matt_resolves_to_allowlisted_role(self):
        identity = resolve_identity("U_MATTJ", self.slack, self.adapter)
        self.assertEqual(identity["email"], "mattj@emtech.us")
        self.assertEqual(identity["role"], "admin")

    def test_slack_user_with_no_matching_email_is_refused(self):
        # FakeSlackClient.lookup_user_email returns None for anyone not in its
        # FAKE_SLACK_USERS map -- e.g. a guest account.
        identity = resolve_identity("U_UNKNOWN_GUEST", self.slack, self.adapter)
        self.assertIsNone(identity)

    def test_email_present_in_slack_but_not_in_emblaze_allowlist_is_refused(self):
        # Simulate a Slack user whose email resolves fine but was never added
        # to Emblaze's user list -- guardrail 3.7: never fall back to a default user.
        class _StrayEmailSlackClient(FakeSlackClient):
            def lookup_user_email(self, slack_user_id):
                return "not-in-emblaze@emtech.us"

        identity = resolve_identity("U_STRAY", _StrayEmailSlackClient(), self.adapter)
        self.assertIsNone(identity)


if __name__ == "__main__":
    unittest.main()
