# ADR 0002 -- This app holds no datastore of its own

- **Date:** 2026-07-14
- **Status:** accepted
- **Owner:** Desmond P. (desmondp@emtech.us)
- **Supersedes / Superseded-by:** none

## Context

Emtech's app-author contract (`starthere/platforms/default-stack.md`) asks every app to pick a
datastore from the blessed options: DynamoDB single-table (built against directly) or
Postgres/pgvector (requested from Russell). The new-app checklist and app contract both list
"datastore chosen" as a box to check before handoff.

The Emblaze Slack bot is not a system of record. Per the Emblaze Product Handbook (Part 3.2,
"Reuse, don't reimplement"), the bot's entire job is to let Slack drive the *existing* Emblaze
planner -- plans, quotes, teams -- which already lives in DynamoDB table
`emblaze-prod-planner`, owned and served by `planner_api.py` in the `emblaze` repo. The handbook
is explicit that the bot should call the same functions/endpoints `planner_api.py` already
exposes, not stand up parallel storage.

Today this app runs against `MockPlannerAdapter` (in-memory, no persistence, resets on restart)
because we do not yet have access to the real `emblaze` repo/AWS account. `RealPlannerAdapter` is
now implemented as a real HTTP client (`slack_bot/planner_adapter.py`, see
[ADR 0005](0005-real-planner-adapter-http-client.md)) against the exact `planner_api.py` call or
`/api/planner/*` endpoint each method was originally documented to wrap -- still unverified
against the real API, since that access still hasn't arrived.

## Decision

This app provisions **no datastore of its own** -- no DynamoDB table, no Postgres request to
Russell. All durable planner state (plans, quotes, teams, the quote-number counter, the user
allowlist) continues to live in the existing `emblaze-prod-planner` DynamoDB table and the
`emblaze-prod/sso-users` secret, both owned by the `emblaze` app. This bot is a stateless client
of that data via `PlannerAdapter` (mock today, real once merged/wired), exactly per the
handbook's "the ONE seam to the Emblaze backend" design already in `planner_adapter.py`.

## Alternatives weighed

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Request a new DynamoDB table for this app | Fits the "every app gets its own datastore" default | Duplicates data that already exists and is authoritative in emblaze's table; would immediately diverge (stale plans/quotes, double-counted quote numbers) | Directly contradicts the handbook's explicit "reuse, don't reimplement" rule and the contract's own "read existing data, don't duplicate it" guidance (`starthere/conventions/coding-conventions.md`) |
| Cache planner reads locally to reduce calls into emblaze | Slightly faster `/emblaze status` | Adds a second source of truth to keep in sync, exactly the failure mode DynamoDB `ver` optimistic concurrency exists to prevent | Not worth the complexity for a low-traffic internal Slack bot |

## Consequences

- This app is fully stateless and disposable, same as emblaze itself -- the box (once hosted)
  can be replaced freely with no data loss, since it holds none.
- `RealPlannerAdapter` is implemented as an HTTP client against `/api/planner/*` (this app is
  hosted standalone per [ADR 0003](0003-build-to-starthere-contract-now.md), not merged into the
  `emblaze` process, so a direct function-call implementation isn't an option today) -- never a
  new table. This keeps the math, the counter, the transition rules, and the won-hook as
  literally the same *data*, reached over HTTP instead of via a direct import.
- This app is hosted standalone (not merged into the `emblaze` process), so `RealPlannerAdapter`'s
  outbound HTTP calls need an auth story of their own (a service credential to
  `emblaze.emtech.us`) once this is pointed at a real backend -- that credential does not exist
  yet and is called out as an open item in
  [ADR 0005](0005-real-planner-adapter-http-client.md).
