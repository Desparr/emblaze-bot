import unittest

from slack_bot.planner_adapter import MockPlannerAdapter, TransitionNotAllowed, can_act_on_transition


class CanActOnTransitionTests(unittest.TestCase):
    def test_anyone_can_submit_draft(self):
        self.assertTrue(can_act_on_transition("member", "draft", "pending_l1"))

    def test_member_cannot_approve_l1(self):
        self.assertFalse(can_act_on_transition("member", "pending_l1", "pending_l2"))

    def test_approver_l1_can_approve_l1(self):
        self.assertTrue(can_act_on_transition("approver_l1", "pending_l1", "pending_l2"))

    def test_approver_l1_cannot_approve_l2(self):
        self.assertFalse(can_act_on_transition("approver_l1", "pending_l2", "final_approved"))

    def test_approver_l2_can_approve_either_stage(self):
        self.assertTrue(can_act_on_transition("approver_l2", "pending_l1", "pending_l2"))
        self.assertTrue(can_act_on_transition("approver_l2", "pending_l2", "final_approved"))

    def test_admin_outranks_everyone(self):
        self.assertTrue(can_act_on_transition("admin", "pending_l2", "final_approved"))

    def test_unknown_transition_is_rejected(self):
        self.assertFalse(can_act_on_transition("admin", "draft", "final_approved"))


class MockPlannerAdapterTransitionTests(unittest.TestCase):
    def setUp(self):
        self.adapter = MockPlannerAdapter()
        quote = self.adapter.create_quote(
            {"name": "Test Quote", "quoteNumber": 1, "approvalStatus": "draft"}, "alex@emtech.us"
        )
        self.quote_id = quote["id"]
        self.ver = quote["ver"]

    def test_member_cannot_jump_straight_to_approved(self):
        with self.assertRaises(TransitionNotAllowed):
            self.adapter.transition_quote(self.quote_id, "final_approved", self.ver, "alex@emtech.us")

    def test_l1_approver_can_advance_pending_quote(self):
        self.adapter.transition_quote(self.quote_id, "pending_l1", self.ver, "alex@emtech.us")
        quote = self.adapter.get_quote(self.quote_id)
        self.adapter.transition_quote(self.quote_id, "pending_l2", quote["ver"], "priya@emtech.us")
        self.assertEqual(self.adapter.get_quote(self.quote_id)["body"]["approvalStatus"], "pending_l2")

    def test_stale_version_is_rejected(self):
        self.adapter.transition_quote(self.quote_id, "pending_l1", self.ver, "alex@emtech.us")
        with self.assertRaises(ValueError):
            self.adapter.transition_quote(self.quote_id, "pending_l1", self.ver, "alex@emtech.us")


if __name__ == "__main__":
    unittest.main()
