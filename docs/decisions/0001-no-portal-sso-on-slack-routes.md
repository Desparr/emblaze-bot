# ADR 0001 -- Portal SSO is not applied to the Slack webhook routes

- **Date:** 2026-07-14
- **Status:** accepted
- **Owner:** Desmond P. (desmondp@emtech.us)
- **Supersedes / Superseded-by:** none

## Context

Emtech's app-author contract (`Emtech-LLC/starthere`) requires every hosted app to consume
portal SSO: verify the `orbit_session` cookie against the portal JWKS, redirect unauthenticated
**pages** to the portal's authorize URL, and return **401** on unauthenticated `/api/*` calls
(`starthere/platforms/platform-services.md`, `building/app-contract.md`).

This app (the Emblaze Slack bot) exposes exactly three HTTP routes: `GET /healthz` / `GET
/health` (already exempt from any auth gate by contract), `POST /slack/commands`, and `POST
/slack/interactions`. The latter two are never called by a human's browser -- they are called
directly by Slack's servers as slash-command and interactivity webhooks. Slack authenticates
itself to us with its own scheme (`verify.py`): an HMAC-SHA256 signature over the raw request
body, computed with the app's Slack signing secret, plus a timestamp check for replay
protection (handbook 3.3). Slack has no concept of, and can never present, an `orbit_session`
cookie -- it is not a browser and does not participate in Emtech's SSO flow.

There is no other surface in this app: no dashboard, no admin page, no route a person visits
directly in a browser.

## Decision

We do **not** wire the portal-SSO rung into this app. `/slack/commands` and `/slack/interactions`
continue to authenticate exclusively via Slack's HMAC signature verification (already
guardrail 3.7 in the Emblaze handbook: verify the signature before reading anything else).
The `PORTAL_SSO_*` / `AUTH_REQUIRE` env vars are listed in `.env.example`, commented out, so the
door stays open if this app ever grows a human-facing page.

If a human-facing page is ever added to this app (e.g. an admin view of pending approvals), that
specific page must consume portal SSO per the standard contract at that time -- this ADR only
covers the current all-webhook route set.

## Alternatives weighed

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Gate `/slack/commands` and `/slack/interactions` behind portal SSO anyway | Contract compliance by the letter | Slack can never present an `orbit_session` cookie -- this would make every legitimate Slack request fail with a 401 or a redirect, breaking the bot entirely | Functionally incompatible with what these routes are for |
| Build a thin proxy/exception rule that skips SSO only for requests bearing a valid Slack signature | Keeps a single unified auth rung conceptually | Reinvents exactly what Slack signature verification already does, adds complexity with no security benefit -- signature verification *is* the appropriate authentication for a server-to-server webhook | Redundant; the existing mechanism is already correct and tested |

## Consequences

- This app's two functional routes remain authenticated by Slack's HMAC signature only, as
  originally specified in the Emblaze Product Handbook Part 3 -- no change to `verify.py`,
  `routes.py`, or `identity.py`.
- If this app later grows any browser-facing page, that page (and only that page) must add the
  portal-SSO rung; this ADR's scope does not extend to it automatically.
- `PORTAL_SSO_ISSUER` ships commented out in `.env.example` per the fail-closed convention (a
  set-but-blank value would otherwise be a silent no-op instead of a hard startup error).
