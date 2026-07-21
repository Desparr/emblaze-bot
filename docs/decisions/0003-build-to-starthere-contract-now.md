# ADR 0003 -- Build this app to the starthere contract now, independent of the emblaze merge

- **Date:** 2026-07-14
- **Status:** accepted
- **Owner:** Desmond P. (desmondp@emtech.us)
- **Supersedes / Superseded-by:** none

## Context

The Emblaze Product Handbook (Part 3.2, "Merging into emblaze") originally scoped this bot as
code that gets copied into the existing `github.com/Emtech-LLC/emblaze` repo -- it would inherit
emblaze's already-hosted Dockerfile, health endpoint, and deploy pipeline, and never need its own.

We since found `Emtech-LLC/starthere`, Emtech's general app-author contract: any new Emtech app
gets its own repo, its own `Dockerfile` (base `public.ecr.aws/*`, health endpoint, env-var
config), gets handed to Russell Goodrick for a one-time hosting setup, and then ships itself on
every push to `main`. We do not yet have access to the real `emblaze` repo or AWS account
(tracked in [0002](0002-no-independent-datastore.md)), so the original "merge into emblaze" path
is blocked on that access, with no ETA.

## Decision

Build this app to the `starthere` contract as its own standalone, hostable Emtech app:
`Dockerfile`, `.dockerignore`, `.env.example`, `.gitignore`/`.gitattributes` (LF), a `/healthz`
+ `/health` endpoint, and `README.md`/`CLAUDE.md` in house style -- all added in this change.
This does not abandon the original "merge into emblaze" plan; it means we are no longer blocked
on repo access to make forward progress and get this bot in front of real Slack users. Whichever
happens first -- repo access to `emblaze` arrives, or this app gets handed to Russell as its own
service -- should work from here: the `slack_bot/` package is unchanged either way, only the
hosting shell around it (this Dockerfile/README/etc.) would be discarded if/when it merges into
emblaze's own container.

## Alternatives weighed

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Wait for `emblaze` repo/AWS access before doing any hosting work | No throwaway Dockerfile/README work if the merge happens soon | Open-ended wait with no ETA; the bot can't be demoed or tested against real Slack in the meantime | Blocks all forward progress on an external dependency with no timeline |
| Build to the contract, but skip the parts that only matter once actually handed to Russell (e.g. Dockerfile) | Less work right now | Contradicts the explicit ask to "run through starthere and adjust the bot as needed"; leaves the repo not actually hostable if we do want to hand it off soon | Half-measure that doesn't resolve the underlying blocker either |

## Consequences

- This repo is now hostable on its own merit: if handed to Russell today, it satisfies the
  `building/app-contract.md` checklist except for the portal-SSO/Orbit-chrome items, which
  [ADR 0001](0001-no-portal-sso-on-slack-routes.md) deliberately scopes out as not applicable to
  an all-webhook route set.
- The git repo root was moved from `slack_bot/` up to this app's true root (`emblaze-bot/`) in
  the same change, since Russell's handoff model expects `Dockerfile`/`README.md`/`CLAUDE.md` at
  the top of the repo he's given, not nested inside a subpackage.
- If/when real `emblaze` repo access arrives and the original merge plan proceeds, this
  Dockerfile/CLAUDE.md/ADR set is disposable -- the `slack_bot/` package (and the
  `RealPlannerAdapter` work in [0002](0002-no-independent-datastore.md)) is what actually carries
  over.
