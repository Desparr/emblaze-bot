# ADR 0004 -- Day-based scheduling on the plan modal's technician line

- **Date:** 2026-07-21
- **Status:** accepted
- **Owner:** Desmond P. (desmondp@emtech.us)
- **Supersedes / Superseded-by:** none

## Context

The plan modal's technician line originally only collected a week range (`weeks_block` ->
`activeWeeks`, e.g. `1-10`). An earlier "By day" scheduling option existed once but was removed
before v1 shipped (see git history and the CLAUDE.md/README "known gaps" notes it left behind):
it wrote `technician.scheduleUnit = "day"` on the project body without ever collecting matching
per-technician day data, so `math_utils.py`'s cost math had nothing to price a day-mode plan
with -- it would have silently priced it as if `activeWeeks` were still present (i.e. wrongly,
or not at all). Removing the option was the correct fix at the time; it just meant Slack-created
plans could never be day-scheduled.

Separately, `math_utils.tech_cost()` already contained a day-mode branch
(`if tech.get("activeDays") is not None: ...`) and a passing unit test
(`test_day_mode_divides_weekly_rate_by_five`) exercising it with calendar-date strings as
`activeDays`. That formula -- one calendar day of a technician's time costs
`weekly_rate / WORKDAYS_PER_WEEK` (5) -- was already correct and already tested; the missing
piece was purely the Slack-side UI and parsing to *collect* `activeDays` in the first place.

## Decision

Add a real per-technician day-picker to the plan modal and wire it end-to-end:

1. **Block Kit (`blocks.py`):** a new `schedule_mode_block` (`static_select`, options "Week
   range" / "Specific days", defaulting to "Week range") picks which of two fields is
   authoritative: the existing `weeks_block` (text input, `1-10` style) or a new `days_block`
   (a `checkboxes` element, `DAY_OPTIONS` = Mon-Sun). Both `weeks_block` and `days_block` are
   marked `optional` at the Block Kit level -- only the field matching the selected mode is
   validated in `interactions.py`; the other is ignored, not required, so the modal doesn't
   force filling in a field that isn't relevant to the chosen mode.
2. **Data shape:** a technician line now always carries a `scheduleUnit` (`"week"` or `"day"`)
   alongside either `activeWeeks` (a list of week-number ints, unchanged) or `activeDays` (a
   list of lowercase 3-letter weekday abbreviations, e.g. `["mon", "wed", "fri"]`) -- never
   both. `scheduleUnit` and the day/week list live **on the technician object**, not at the top
   of the project body, mirroring where `activeWeeks` already lived in
   `MockPlannerAdapter`'s seed data. This means a single project can in principle carry a mix of
   week-scheduled and day-scheduled technician lines (the math is additive per line either way).
3. **Parsing (`interactions.py`):** `_submit_plan` reads `schedule_mode_block`, then parses
   *only* the matching field: `weeks_block` via the existing `math_utils.parse_week_range()` for
   week mode, or the `days_block` checkboxes' `selected_options` for day mode. Day mode requires
   at least one day selected (mirrors week mode's "at least one week" rule); an invalid/garbage
   value in the *other* field is not an error, since it's not the active mode.
4. **Math (`math_utils.py`):** no formula change was needed -- `tech_cost()` already implemented
   `day_rate = weekly_rate / WORKDAYS_PER_WEEK; quantity * day_rate * len(activeDays)`, which is
   agnostic to what's *in* `activeDays` (calendar dates or weekday abbreviations both just get
   counted with `len()`). New tests were added
   (`tests/test_math_utils.py::test_day_mode_with_weekday_abbreviations_and_night_shift`,
   `test_day_mode_and_week_mode_technicians_combine_on_one_project`,
   `test_grand_total_for_a_day_mode_plan`) to pin down *this* chosen shape (weekday
   abbreviations) specifically, alongside the pre-existing calendar-date test.

## Alternatives weighed

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| `activeDays` as full ISO calendar dates (matching the pre-existing `test_day_mode_divides_weekly_rate_by_five` test's fixture) | Maps directly onto an actual project calendar; no ambiguity about "which week's Monday" | A Slack modal per-technician date-multi-picker across an entire project's date range is a poor Block Kit fit (no native "select N dates" element); would require a much heavier custom UI | Doesn't fit Slack's Block Kit primitives well for this input |
| Weekday abbreviations (`["mon", "wed", "fri"]`), applied to every week in the project's date range | Maps onto a native Block Kit `checkboxes` element (7 fixed options); easy to build, easy to validate, easy to read back in the app | Doesn't pin an exact calendar day -- "which Mondays" is implicit (the whole project date range) rather than explicit | Chosen: the Block Kit fit and the "at least one day, no ambiguity about the intent" property outweigh not being calendar-exact; `math_utils.py`'s formula doesn't care either way since it only counts `len(activeDays)` |
| Keep day-scheduling app-only (Slack still only creates week-mode plans) | Zero risk of reintroducing the old bug | Leaves the gap this ADR exists to close; the task explicitly asked for a *correct* day-mode implementation, not another removal | Doesn't meet the requirement |

## Consequences

- `README.md`'s "Known gaps" entry for day-scheduling and `CLAUDE.md`'s matching gotcha are both
  updated to say this is implemented, with a pointer to this ADR for the shape.
- Any future work that reads `activeDays` (the real `emblaze` app, reports, `RealPlannerAdapter`)
  must treat it as a list of `mon`/`tue`/`wed`/`thu`/`fri`/`sat`/`sun` strings when produced by
  this bot's plan modal -- **not** calendar dates. If the real `emblaze` planner's own UI already
  uses a different `activeDays` convention (e.g. calendar dates, per the original mock test
  fixture), that mismatch must be reconciled before `RealPlannerAdapter` is trusted with day-mode
  plans in production -- flagged here rather than silently guessed, per the handbook's own "if
  this doc and the code disagree, the code wins" rule applied in reverse (the code is only as
  right as this ADR's assumption).
- A technician line can mix `scheduleUnit` values within one project (one line "week", another
  "day") -- this was already implicitly possible in the data model and is now exercised by a
  test; no additional validation was added to forbid or require uniformity across lines.
