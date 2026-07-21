# ADR 0005 -- RealPlannerAdapter is an HTTP client, unverified against the real API

- **Date:** 2026-07-21
- **Status:** proposed
- **Owner:** Desmond P. (desmondp@emtech.us)
- **Supersedes / Superseded-by:** none

## Context

`planner_adapter.py` has always shipped `RealPlannerAdapter` as a skeleton: every method raised
`NotImplementedError` with a comment naming the `planner_api.py` function or `/api/planner/*`
HTTP endpoint (handbook 2.5) it was expected to wrap once this bot had access to the real
`emblaze` repo. That access still hasn't arrived, and per
[ADR 0003](0003-build-to-starthere-contract-now.md) this app is being hosted standalone rather
than merged into the `emblaze` process -- meaning even *if* repo access arrived, a direct
Python-level function import (the handbook's originally preferred approach, per
[ADR 0002](0002-no-independent-datastore.md)) isn't available today; only an HTTP call to
`emblaze.emtech.us` is.

The task that produced this ADR explicitly ruled out waiting for real API access: implement
`RealPlannerAdapter` as a working HTTP client now, against the exact endpoint paths already named
in the old skeleton's comments, reshaping responses to match `MockPlannerAdapter`'s exact
return shapes (since `blocks.py`/`commands.py`/`interactions.py`/`approvals.py` are all written
against those shapes and must not need to change regardless of which adapter is wired in).

## Decision

`RealPlannerAdapter` (`slack_bot/planner_adapter.py`) is now a real HTTP client using `requests`
(already a dependency via `slack_client.py` and `requirements.txt`) against `EMBLAZE_BASE_URL`.
Every one of the 13 `PlannerAdapter` abstract methods is implemented, calling one `/api/planner/*`
path each (full map in the class docstring), with responses reshaped to match
`MockPlannerAdapter`'s return shapes exactly:

- Simple reads (`get_users`, `list_projects`, `list_clients`, `get_project`, `get_client`,
  `list_quotes`, `get_quote`) are assumed to already return the right shape and are passed
  through as-is; a 404 is translated to `KeyError`, matching the mock's contract.
- `get_tier_weekly_rates` reshapes an assumed `{"services": [{"tier": N, "weeklyRate": R}, ...]}`
  config response into `{tier_int: weekly_rate}`.
- Writes (`create_project`, `update_project`, `create_quote`, `allocate_quote_number`,
  `transition_quote`) POST/PUT a JSON body of `{body, ver?, actorEmail, ...}` and return
  `{id, ver}` / `{ver}` / `{quoteNumber}` shapes matching the mock. `update_project` and
  `transition_quote` translate a `409` response into `ValueError` (matching the mock's
  stale-`ver` `ValueError`), not a raw HTTP exception, so callers in `interactions.py` don't need
  an adapter-specific `except` clause.
- `transition_quote` performs the same bot-side role check `MockPlannerAdapter` does (defense in
  depth, guardrail 3.7) *before* calling the transition endpoint: it reads the quote and the
  users list first, and raises `TransitionNotAllowed` locally if `can_act_on_transition()` fails,
  without ever making the write call. A `403` from the server is also translated to
  `TransitionNotAllowed` as a second line of defense.

The class carries a large, explicit **"UNVERIFIED -- READ BEFORE USING IN PRODUCTION"** comment
block at its top, naming every assumed endpoint path and response shape, and stating plainly that
a human with real `emblaze`/`planner_api.py` access must check and correct it before
`PLANNER_ADAPTER=real` is used anywhere that matters. **That comment block must not be removed**
when this class is edited -- update it in place (e.g. to record who verified it and when) instead.
This is why this ADR's Status is `proposed`, not `accepted`: it records a real, working
implementation, but one whose correctness against the actual backend is not yet established.

`tests/test_real_planner_adapter.py` unit-tests all 13 methods against a fake, injectable
`requests`-shaped session (no live backend), asserting the HTTP method, path, and request/response
shape for each -- so the wiring itself is verified even though the shapes it assumes are not.

## Alternatives weighed

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Leave `RealPlannerAdapter` as a `NotImplementedError` skeleton until real API access arrives | Zero risk of shipping wrong assumptions | Leaves an untested, unusable adapter indefinitely; the task explicitly asked for a working implementation now | Doesn't meet the requirement; also leaves the HTTP-wiring layer itself (auth headers, error translation, timeouts) completely unexercised |
| Implement as direct Python imports of `planner_api.py` functions (the handbook's original preference) | Matches handbook 2.5/3.2's stated intent; no network hop | Requires this code to run in the same process as `planner_api.py`, i.e. actually merged into the `emblaze` repo -- not possible while this app is hosted standalone (ADR 0003) | Not available in the current hosting model |
| Guess wildly different response shapes per method instead of mirroring the mock | N/A | Would force `blocks.py`/`commands.py`/`interactions.py` to branch on which adapter is active, defeating the entire point of the `PlannerAdapter` seam | Explicitly ruled out by the task |

## Consequences

- `PLANNER_ADAPTER=real` is usable today in the sense that it will make real HTTP calls and not
  crash -- but every path/shape is a guess pending verification, so it must not be pointed at a
  real, mutating backend without that check happening first.
- The next person with real `emblaze` repo access has a fast, mechanical task: read
  `planner_api.py`, compare it against the endpoint map in `RealPlannerAdapter`'s docstring, fix
  any mismatches in the same PR as updating this ADR's Status to `accepted` (or recording what
  changed if `superseded`).
- Outbound HTTP calls to `EMBLAZE_BASE_URL` will need a service credential (bearer token, mTLS,
  or network allowlist) once pointed at a real, protected backend -- no such credential exists
  yet. This is the same open item [ADR 0002](0002-no-independent-datastore.md) flagged; it
  remains unresolved and should get its own follow-up ADR when decided, rather than being
  silently added here.
- `requests` was already a `requirements.txt` dependency (used by `slack_client.py`); no new
  third-party package was added for `RealPlannerAdapter` itself. Its tests use only
  `unittest.mock`-free hand-written fakes (no new test dependency either).
