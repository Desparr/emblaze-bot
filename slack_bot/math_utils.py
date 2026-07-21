"""The math from handbook Part 2.3, reused so Slack's confirmation messages show
real dollars instead of a placeholder. Keep this in lockstep with planner_api.py --
if the two ever disagree, planner_api.py is the source of truth.

Day-scheduling (2026-07-21, see docs/decisions/0004-day-based-plan-scheduling.md):
a technician line is either week-scheduled (`activeWeeks`: a list of week numbers)
or day-scheduled (`activeDays`: a list of weekday abbreviations, e.g.
`["mon", "wed", "fri"]`, chosen per technician in the plan modal's day-picker --
see blocks.py's DAY_OPTIONS). There is no per-technician `scheduleUnit` rate table
of its own; day-mode cost is derived from the *same* weekly rate table, divided
evenly across a 5-day work week (`WORKDAYS_PER_WEEK`), so switching a technician
between week- and day-scheduling never requires a separate pricing config.
"""

from __future__ import annotations

NIGHT_SHIFT_WEEKLY_SURCHARGE = 400
WORKDAYS_PER_WEEK = 5


def _tech_rate(tier_weekly_rates: dict, tech: dict) -> float:
    weekly_rate = tier_weekly_rates[tech["tier"]]
    if tech.get("nightShift"):
        weekly_rate += NIGHT_SHIFT_WEEKLY_SURCHARGE
    return weekly_rate


def tech_cost(tier_weekly_rates: dict, tech: dict) -> float:
    """Week mode: quantity * weekly_rate * len(activeWeeks).
    Day mode (`tech["activeDays"]` present): quantity * (weekly_rate / 5) *
    len(activeDays) -- one calendar day of a technician's time costs 1/5th of
    their weekly rate, so a 5-day week costs exactly the same either way.
    """
    rate = _tech_rate(tier_weekly_rates, tech)
    if tech.get("activeDays") is not None:
        day_rate = rate / WORKDAYS_PER_WEEK
        return tech["quantity"] * day_rate * len(tech["activeDays"])
    return tech["quantity"] * rate * len(tech.get("activeWeeks", []))


def project_labor_cost(tier_weekly_rates: dict, project_body: dict) -> float:
    return sum(tech_cost(tier_weekly_rates, tech) for tech in project_body.get("technicians", []))


def quote_totals(
    tier_weekly_rates: dict,
    project_bodies: list,
    *,
    mgmt_fee_percent: float = 0,
    supp_fee_percent: float = 0,
    travel_items: list | None = None,
    electrical_items: list | None = None,
    tools_items: list | None = None,
    incidentals_items: list | None = None,
) -> dict:
    labor = sum(project_labor_cost(tier_weekly_rates, p) for p in project_bodies)
    mgmt = round(labor * mgmt_fee_percent / 100)
    supp = round(labor * supp_fee_percent / 100)

    items_total = 0.0
    for item in travel_items or []:
        items_total += item["days"] * item["rate"]
    for item in (electrical_items or []) + (tools_items or []) + (incidentals_items or []):
        items_total += item["qty"] * item["rate"]

    grand_total = labor + mgmt + supp + items_total
    return {
        "labor": labor,
        "mgmt": mgmt,
        "supp": supp,
        "items": items_total,
        "grandTotal": grand_total,
    }


def parse_week_range(text: str) -> list:
    """'1-10' or '1-4,7-9' -> [1,2,...,10] / [1,2,3,4,7,8,9]. Handbook 3.5."""
    weeks = set()
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_str, end_str = chunk.split("-", 1)
            start, end = int(start_str), int(end_str)
            if start > end:
                start, end = end, start
            weeks.update(range(start, end + 1))
        else:
            weeks.add(int(chunk))
    return sorted(weeks)
