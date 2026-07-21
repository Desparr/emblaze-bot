import unittest

from slack_bot.math_utils import parse_week_range, project_labor_cost, quote_totals

TIER_RATES = {5: 6000, 4: 5200, 3: 4400, 2: 3600, 1: 2800, 6: 0}


class ParseWeekRangeTests(unittest.TestCase):
    def test_simple_range(self):
        self.assertEqual(parse_week_range("1-10"), list(range(1, 11)))

    def test_multiple_ranges_and_singles(self):
        self.assertEqual(parse_week_range("1-4,7-9,12"), [1, 2, 3, 4, 7, 8, 9, 12])

    def test_dedupes_and_sorts_overlaps(self):
        self.assertEqual(parse_week_range("5-7,1-3,6"), [1, 2, 3, 5, 6, 7])

    def test_reversed_range_is_normalized(self):
        self.assertEqual(parse_week_range("10-8"), [8, 9, 10])

    def test_empty_string(self):
        self.assertEqual(parse_week_range(""), [])


class ProjectLaborCostTests(unittest.TestCase):
    def test_week_mode_matches_handbook_worked_example(self):
        # handbook 2.6 worked example: 2x T3, 10 active weeks, no night shift
        project_body = {
            "technicians": [
                {"tier": 3, "quantity": 2, "nightShift": False, "activeWeeks": list(range(1, 11))}
            ]
        }
        # 2 * 4400 * 10 = 88000
        self.assertEqual(project_labor_cost(TIER_RATES, project_body), 88000)

    def test_night_shift_surcharge(self):
        project_body = {
            "technicians": [{"tier": 1, "quantity": 1, "nightShift": True, "activeWeeks": [1]}]
        }
        self.assertEqual(project_labor_cost(TIER_RATES, project_body), 2800 + 400)

    def test_day_mode_divides_weekly_rate_by_five(self):
        project_body = {
            "technicians": [
                {"tier": 5, "quantity": 1, "nightShift": False, "activeDays": ["2026-08-03", "2026-08-04"]}
            ]
        }
        self.assertEqual(project_labor_cost(TIER_RATES, project_body), (6000 / 5) * 2)

    def test_day_mode_with_weekday_abbreviations_and_night_shift(self):
        # docs/decisions/0004-day-based-plan-scheduling.md: the plan modal's
        # day-picker writes activeDays as lowercase weekday abbreviations
        # (["mon", "wed", "fri"]), not calendar dates. project_labor_cost only
        # ever counts len(activeDays), so the formula is agnostic to which
        # convention produced the list -- this pins down *our* chosen shape.
        project_body = {
            "technicians": [
                {
                    "tier": 5,
                    "quantity": 2,
                    "nightShift": True,
                    "scheduleUnit": "day",
                    "activeDays": ["mon", "wed", "fri"],
                }
            ]
        }
        # weekly rate 6000 + 400 night surcharge = 6400/wk -> day rate 1280/day
        # 2 techs * 1280 * 3 days = 7680
        self.assertEqual(project_labor_cost(TIER_RATES, project_body), (6000 + 400) / 5 * 2 * 3)

    def test_day_mode_and_week_mode_technicians_combine_on_one_project(self):
        # A project can (in principle) carry more than one technician line,
        # some week-scheduled and some day-scheduled -- the total is additive.
        project_body = {
            "technicians": [
                {"tier": 3, "quantity": 1, "nightShift": False, "scheduleUnit": "week", "activeWeeks": [1, 2]},
                {"tier": 4, "quantity": 1, "nightShift": False, "scheduleUnit": "day", "activeDays": ["mon", "tue"]},
            ]
        }
        # week line: 4400 * 2 = 8800
        # day line: (5200 / 5) * 2 = 2080
        self.assertEqual(project_labor_cost(TIER_RATES, project_body), 8800 + 2080)


class QuoteTotalsTests(unittest.TestCase):
    def test_grand_total_includes_fees_and_items(self):
        project_body = {
            "technicians": [{"tier": 3, "quantity": 2, "nightShift": False, "activeWeeks": list(range(1, 11))}]
        }
        totals = quote_totals(
            TIER_RATES,
            [project_body],
            mgmt_fee_percent=10,
            supp_fee_percent=8,
            travel_items=[{"days": 5, "rate": 100}],
        )
        self.assertEqual(totals["labor"], 88000)
        self.assertEqual(totals["mgmt"], 8800)
        self.assertEqual(totals["supp"], 7040)
        self.assertEqual(totals["items"], 500)
        self.assertEqual(totals["grandTotal"], 88000 + 8800 + 7040 + 500)

    def test_grand_total_for_a_day_mode_plan(self):
        project_body = {
            "technicians": [
                {"tier": 5, "quantity": 1, "nightShift": False, "scheduleUnit": "day", "activeDays": ["mon", "tue", "wed"]}
            ]
        }
        totals = quote_totals(TIER_RATES, [project_body], mgmt_fee_percent=10, supp_fee_percent=0)
        # labor = (6000/5) * 3 = 3600
        self.assertEqual(totals["labor"], 3600)
        self.assertEqual(totals["mgmt"], 360)
        self.assertEqual(totals["grandTotal"], 3600 + 360)


if __name__ == "__main__":
    unittest.main()
