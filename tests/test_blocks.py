import unittest

from slack_bot import blocks


class PlanModalTests(unittest.TestCase):
    def test_plan_modal_has_schedule_mode_and_day_picker_fields(self):
        # docs/decisions/0004-day-based-plan-scheduling.md: the plan modal now
        # offers a real "Schedule by" week/day choice plus a Mon-Sun day-picker,
        # replacing the earlier v1 behavior of never offering day-scheduling.
        view = blocks.plan_modal({5: 6000, 4: 5200, 3: 4400, 2: 3600, 1: 2800, 6: 0}, private_metadata={})
        block_ids = {b.get("block_id") for b in view["blocks"] if "block_id" in b}
        self.assertIn("schedule_mode_block", block_ids)
        self.assertIn("weeks_block", block_ids)
        self.assertIn("days_block", block_ids)

    def test_schedule_mode_defaults_to_week(self):
        view = blocks.plan_modal({5: 6000}, private_metadata={})
        schedule_block = next(b for b in view["blocks"] if b.get("block_id") == "schedule_mode_block")
        self.assertEqual(schedule_block["element"]["initial_option"]["value"], "week")

    def test_day_picker_offers_seven_weekday_options(self):
        view = blocks.plan_modal({5: 6000}, private_metadata={})
        days_block = next(b for b in view["blocks"] if b.get("block_id") == "days_block")
        values = [opt["value"] for opt in days_block["element"]["options"]]
        self.assertEqual(values, ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])

    def test_weeks_and_days_blocks_are_optional_so_only_the_active_mode_is_required(self):
        view = blocks.plan_modal({5: 6000}, private_metadata={})
        weeks_block = next(b for b in view["blocks"] if b.get("block_id") == "weeks_block")
        days_block = next(b for b in view["blocks"] if b.get("block_id") == "days_block")
        self.assertTrue(weeks_block["optional"])
        self.assertTrue(days_block["optional"])

    def test_plan_modal_tier_options_are_sorted_highest_first(self):
        view = blocks.plan_modal({5: 6000, 3: 4400, 1: 2800}, private_metadata={})
        tier_block = next(b for b in view["blocks"] if b.get("block_id") == "tier_block")
        values = [opt["value"] for opt in tier_block["element"]["options"]]
        self.assertEqual(values, ["5", "3", "1"])


class QuoteModalTests(unittest.TestCase):
    def test_empty_projects_and_clients_produce_placeholder_options(self):
        view = blocks.quote_modal([], [], private_metadata={})
        plan_block = next(b for b in view["blocks"] if b.get("block_id") == "plan_block")
        client_block = next(b for b in view["blocks"] if b.get("block_id") == "client_block")
        self.assertEqual(plan_block["element"]["options"][0]["value"], "__none__")
        self.assertEqual(client_block["element"]["options"][0]["value"], "__none__")


class StatusMessageTextTests(unittest.TestCase):
    def test_all_zero_counts_render_without_waiting_lines(self):
        text = blocks.status_message_text({}, [])
        self.assertIn("won 0", text)
        self.assertIn("drafts 0", text)
        self.assertNotIn("waiting on", text)

    def test_waiting_lines_are_appended_below_the_summary(self):
        text = blocks.status_message_text({"pending": 1}, ["#1519 Vulcan… ⏳ waiting on L1"])
        self.assertIn("pending 1", text)
        self.assertIn("waiting on L1", text)


if __name__ == "__main__":
    unittest.main()
