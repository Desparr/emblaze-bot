# ADR 0006 -- Quotes are for internal Emtech teams/departments, not external clients

- **Date:** 2026-07-21
- **Status:** accepted
- **Owner:** Desmond P. (desmondp@emtech.us)
- **Supersedes / Superseded-by:** none

## Context

Every earlier version of this bot (`planner_adapter.py`'s `PlannerAdapter` ABC and both its
implementations, `blocks.py`'s quote modal, `commands.py`, `interactions.py`, `approvals.py`, the
tests, and the docs) modeled the "who is this quote for" concept as a **client** -- an external
company such as "Amazon" or "Vulcan Inc" -- with `list_clients()`/`get_client(client_id)` methods,
a `client_id` flowing through the quote-creation flow, a Block Kit field labeled "Client", and
`MockPlannerAdapter` seed data named `client-1`/`client-2` ("Amazon"/"Vulcan Inc").

Desmond clarified on 2026-07-21 that this is wrong: the Emblaze planner's quotes/contracts are
built **for internal Emtech teams/departments** (e.g. Field Operations, Engineering) -- not for
external client companies. There is no external-client relationship in this product at all; the
"client" language in the code was a mismodeling of an internal team/department concept, not a
simplification of a real client concept.

This is purely a naming/domain-modeling fix. It does not touch the approval chain: `ROLE_RANK`,
`TRANSITION_RULES`, `role_meets()`, `can_act_on_transition()`, and `MockPlannerAdapter`'s `_users`
seed data are all internal Emtech roles (`member` -> `approver_l1` -> `approver_l2` -> `admin`)
and are unaffected by this rename.

## Decision

Rename the "client" concept to "team" end-to-end:

- `PlannerAdapter` ABC (`slack_bot/planner_adapter.py`): `list_clients()` -> `list_teams()`,
  `get_client(client_id)` -> `get_team(team_id)`. Both `MockPlannerAdapter` and
  `RealPlannerAdapter` updated to match.
- `client_id` -> `team_id` everywhere it flowed through the quote-creation path: the quote modal's
  Block Kit `block_id`/`action_id` (`client_block`/`client_input` -> `team_block`/`team_input`),
  `interactions.py`'s `_submit_quote`/`_create_quote_and_confirm`, and the quote body's `client`
  field -> `team`.
- Block Kit label text changed from "Client" to "Team" (the quote modal's field label and the
  approval DM's "Client: *{client}*" line -> "Team: *{team}*").
- `MockPlannerAdapter`'s seed data renamed from `client-1`/`client-2` ("Amazon"/"Vulcan Inc") to
  `team-1`/`team-2` ("Field Operations"/"Engineering"). **These two names are placeholders** --
  Desmond should replace them with the real internal team/department names once known.
- `RealPlannerAdapter`'s guessed HTTP endpoint paths renamed from `/api/planner/clients` and
  `/api/planner/clients/<id>` to `/api/planner/teams` and `/api/planner/teams/<id>`. This rename
  is exactly as unverified as every other endpoint path in that class's existing "UNVERIFIED"
  notice -- the notice was extended to say so explicitly, rather than implying the rename itself
  had somehow been checked against the real API.
- All tests referencing the old names (`tests/test_blocks.py`, `tests/test_interactions.py`,
  `tests/test_real_planner_adapter.py`) updated to the new names/ids/labels; test count and
  coverage unchanged (only names inside existing tests changed, no tests removed).
- `README.md` and `CLAUDE.md` prose reviewed; the one substantive business-language reference
  found ("client accepted" in README's known-gaps section, describing what `approved` might mean)
  was changed to "team accepted". The many other "client" occurrences in both docs
  (`SlackClient`, `FakeSlackClient`, "HTTP client") refer to the *Slack/HTTP client* sense of the
  word, not the business concept, and were left as-is.
- `docs/decisions/0002-no-independent-datastore.md` and
  `docs/decisions/0005-real-planner-adapter-http-client.md` updated where they listed "clients" as
  planner data alongside "plans, quotes" or named `list_clients`/`get_client` in prose.

## Alternatives weighed

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Keep "client" naming, just document that it means "internal team" | Zero code churn | Leaves permanently misleading names in the ABC, Block Kit labels, and seed data; the next person to touch this code (or the real `emblaze` backend author) would reasonably assume external-client support was intended | Doesn't fix the actual problem, only papers over it |
| Rename to "department" instead of "team" | Also accurate | Task explicitly asked for one consistent term; "team" was specified | Not chosen per explicit instruction to standardize on "Team" |
| Rename to "team" end-to-end (chosen) | Matches the real domain; one consistent label across Block Kit, code, and docs | Touches many files; seed data names are still placeholders pending real values | Chosen: correctness of the domain model outweighs the churn, and the change is mechanical/low-risk since it doesn't touch approval-chain logic |

## Consequences

- Anyone extending the quote-creation flow should use `team`/`team_id`/`list_teams`/`get_team`
  going forward; there is no external-client concept anywhere in this bot.
- The seed team names ("Field Operations", "Engineering") in `MockPlannerAdapter` are placeholders
  and should be replaced with real Emtech team/department names before this is treated as
  representative sample data.
- `RealPlannerAdapter`'s `/api/planner/teams` path is a guess, exactly like every other endpoint
  path in that class -- it must still be checked against the real `emblaze` `planner_api.py`
  source per [ADR 0005](0005-real-planner-adapter-http-client.md) before production use, and that
  check should also confirm the real API's own name for this concept (it may not be "teams"
  either).
- The approval chain (`ROLE_RANK`, `TRANSITION_RULES`, `role_meets()`,
  `can_act_on_transition()`, and the `_users` seed data) was not touched by this change in any way.
