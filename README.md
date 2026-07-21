# Emblaze Slack Bot

An implementation of **Part 3** of the Emblaze Product Handbook: a Slack app
that lets people create plans, quotes, and contracts without opening
[emblaze.emtech.us](https://emblaze.emtech.us).

Built to Emtech's app-author contract (`Emtech-LLC/starthere`) so it can be
handed to Russell Goodrick for hosting as its own small service, independent of
whenever repo access to `emblaze` itself arrives — see
`docs/decisions/0003-build-to-starthere-contract-now.md`. Not yet hosted; run it
locally per below.

> **Working on this repo — as a person or with an AI agent? Read [CLAUDE.md](CLAUDE.md) first.**
> It's the lean agent resolver: env vars, health path, rules, gotchas. This
> README is the human tour.

This was built standalone, without access to the real `emblaze` repo
(`github.com/Emtech-LLC/emblaze`), so it ships with a `MockPlannerAdapter` that
simulates the backend in-memory, a `FakeSlackClient` that logs what it would
send instead of calling `slack.com`, and a `RealPlannerAdapter` HTTP client
(`PLANNER_ADAPTER=real`) that calls `EMBLAZE_BASE_URL`'s `/api/planner/*`
endpoints but is **unverified** against the actual API -- see
`slack_bot/planner_adapter.py`'s `RealPlannerAdapter` docstring and
`docs/decisions/0005-real-planner-adapter-http-client.md` before trusting it
with a real backend. That means the whole request/response flow — signature
verification, identity mapping, modal building, math, approval routing — is
real and tested; only the actual Slack API integration is fully stubbed
(`FakeSlackClient`), and the real planner backend's endpoint shapes are an
educated guess pending verification.

## Layout

```
app.py                     standalone Flask entrypoint; /healthz + /health
Dockerfile                 container build (public.ecr.aws base, binds 0.0.0.0:$PORT)
.dockerignore, .gitignore, .gitattributes   the starthere contract's repo hygiene
slack_bot/
  config.py                env var loading
  verify.py                Slack HMAC signature verification (handbook 3.3)
  slack_client.py          real Slack Web API wrapper
  fake_slack_client.py     offline stand-in that logs instead of calling Slack
  identity.py              Slack user -> Emblaze account mapping (2.4)
  planner_adapter.py       the ONE seam to the Emblaze backend (mock + real HTTP client)
  approvals.py             sends approval DMs when a quote enters pending_l1/l2
  math_utils.py            handbook 2.3's cost math (week- and day-mode) + week-range parsing
  blocks.py                Block Kit builders for the modals/messages (3.5), incl. the day-picker
  commands.py              /emblaze <ping|whoami|status|plan|quote>
  interactions.py          modal submits + Approve/Reject button clicks
  routes.py                the Flask blueprint: /slack/commands, /slack/interactions
tests/                     unit tests (signature verification, math, role rules, commands,
                            interactions, identity, blocks, RealPlannerAdapter's HTTP wiring)
scripts/sign_request.py    signs a request the way Slack would, for local curl testing
docs/decisions/            ADRs -- read these before assuming this app looks like a typical starthere app
```

## Run locally

Requires Python 3.9+ (or Docker, to mirror production).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: for pure local testing you can leave `SLACK_SIGNING_SECRET` as any
string (just make sure `scripts/sign_request.py --secret` matches it) and leave
`SLACK_CLIENT=fake` / `PLANNER_ADAPTER=mock`. You do not need a real Slack app
or `SLACK_BOT_TOKEN` for local testing.

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python app.py     # serves on :8080 (PORT in .env), matching production
```

Or via the container, exactly as it runs in production:

```bash
docker build -t emblaze-bot .
docker run --rm -p 8080:8080 --env-file .env emblaze-bot
curl -i http://localhost:8080/healthz    # expect 200
```

## Configuration

All config and secrets are read from **environment variables** — nothing is
hardcoded or committed. Every variable the app reads is listed in
[`.env.example`](.env.example) (names only, no values); `.env` is gitignored.

| Variable | Required | What it's for |
|---|---|---|
| `PORT` | no (default 8080) | Port the server binds to. |
| `APP_ENV` | no (default `dev`) | `dev` \| `prod`, non-secret. |
| `SLACK_SIGNING_SECRET` | yes | HMAC key Slack signs every request with. |
| `SLACK_BOT_TOKEN` | only if `SLACK_CLIENT=real` | Bot User OAuth token (`xoxb-...`). |
| `SLACK_CLIENT` | no (default `fake`) | `fake` = offline stand-in; `real` = calls slack.com. |
| `SLACK_MAX_REQUEST_AGE_SECONDS` | no (default 300) | Replay-protection window. |
| `PLANNER_ADAPTER` | no (default `mock`) | `mock` = in-memory seeded data; `real` = HTTP client, see caveat below. |
| `EMBLAZE_BASE_URL` | only if `PLANNER_ADAPTER=real` | Where the real Emblaze API lives. |

Real values for a hosted deployment are injected by Russell Goodrick
(Secrets Manager / on-box `.env`) — you never commit them. See
[`docs/decisions/0001-no-portal-sso-on-slack-routes.md`](docs/decisions/0001-no-portal-sso-on-slack-routes.md)
for why `PORTAL_SSO_*` appears commented out rather than wired in.

## Authentication

This app does **not** consume Emtech's portal SSO, unlike most `starthere`
apps — and that's a deliberate, recorded decision, not an oversight. Its only
two functional routes (`/slack/commands`, `/slack/interactions`) are called
directly by Slack's servers, never by a human's browser, and Slack
authenticates itself with its own HMAC-SHA256 request signature (`verify.py`)
rather than a session cookie. See
[`docs/decisions/0001-no-portal-sso-on-slack-routes.md`](docs/decisions/0001-no-portal-sso-on-slack-routes.md).

## Health

`GET /healthz` (alias `GET /health`) returns `200` with a small status JSON —
open, no auth, no downstream calls. Not yet hosted, so there's no live URL to
poll yet; once handed off, tell Russell this path so the deploy poller and
Cloudflare tunnel check the right URL.

## Deploy

Not yet handed off. Once it is: Russell wires up the AWS account, the EC2 box,
the Cloudflare tunnel, and this app's secrets **once** (health path:
`/healthz`; secrets: the vars in `.env.example`). After that, a push to `main`
builds on Linux CI and redeploys automatically (~1–2 min) — watch with
`gh run list` / `gh run watch`. See `Emtech-LLC/starthere` →
`building/how-hosting-works.md` for the full picture.

## Local test loop (no Slack workspace needed)

`scripts/sign_request.py` builds a correctly-HMAC-signed request, the same way
Slack would sign it, so you can drive the whole bot with `curl`. `FakeSlackClient`
comes seeded with four fake Slack users mapped to the four users seeded in
`MockPlannerAdapter`:

| Slack user id | Email | Role |
|---|---|---|
| `U_SIMON` | simonn@emtech.us | admin |
| `U_JOSH` | josh@emtech.us | approver_l2 |
| `U_PRIYA` | priya@emtech.us | approver_l1 |
| `U_ALEX` | alex@emtech.us | member |

With the server running:

```bash
# health check
eval $(.venv/bin/python scripts/sign_request.py commands --text ping --user-id U_SIMON)

# identity mapping
eval $(.venv/bin/python scripts/sign_request.py commands --text whoami --user-id U_JOSH)

# pipeline summary
eval $(.venv/bin/python scripts/sign_request.py commands --text status --user-id U_SIMON)

# opens the plan/quote modals -- the JSON Block Kit view is printed to the server log
eval $(.venv/bin/python scripts/sign_request.py commands --text plan --user-id U_SIMON --channel-id C_TEST)
eval $(.venv/bin/python scripts/sign_request.py commands --text quote --user-id U_SIMON --channel-id C_TEST)
```

To submit a modal or click a button, POST a `view_submission` / `block_actions`
payload to `/slack/interactions` the same way: write the JSON to a file and run
`sign_request.py interactions --payload-file that.json`. This is exactly what
was used to verify plan creation (both week- and day-scheduled), quote creation
+ submission, an L1 approve (which correctly re-notifies L2 approvers), a
member's approve attempt being refused, and a reject-with-note round trip --
all confirmed working end-to-end during development. Grep
`commands.py`/`interactions.py`/`blocks.py` for the `block_id`/`action_id`
names when hand-writing a payload.

Tamper with the signature or send a stale timestamp and you'll get `401` --
that's guardrail 3.7 ("verify the signature before reading anything else").

## Plan scheduling: week or day

The plan modal's "Schedule by" field picks whether a technician line is
week-scheduled (the original `1-10`-style week range, stored as `activeWeeks`)
or day-scheduled (a Mon-Sun checkbox picker, stored as `activeDays`, e.g.
`["mon", "wed", "fri"]`). Both live on the technician object as
`scheduleUnit: "week" | "day"` plus the matching list. Day-mode cost is the
weekly rate divided across a 5-day work week (`math_utils.WORKDAYS_PER_WEEK`),
so a technician scheduled for all 5 weekdays costs exactly the same as one
week-scheduled for that week. Full design rationale, the shape decision, and
the alternatives considered are in
[`docs/decisions/0004-day-based-plan-scheduling.md`](docs/decisions/0004-day-based-plan-scheduling.md).

## Known gaps / verify before going live

These are places where the handbook's Part 3 spec was ambiguous or where a v1
simplification was made. Flagged here rather than silently guessed (bigger
architectural calls are recorded as ADRs in `docs/decisions/` instead):

- **`final_approved -> sent -> approved`**: Part 3 only describes Slack buttons
  for the `pending_l1`/`pending_l2` hops. This bot doesn't drive those two later
  transitions from Slack at all -- confirm against the real transition endpoint
  whether that's intentional (e.g. "sent" = quote doc emailed, "approved" =
  team accepted, both presumably app-side) before adding UI for them.
  See `planner_adapter.py`'s module docstring.
- **`RealPlannerAdapter` is a real HTTP client but its endpoint paths and
  request/response shapes are unverified** against the actual `emblaze`
  `planner_api.py` source -- there was no repo/API access available when it was
  written. See its docstring in `slack_bot/planner_adapter.py` and
  [`docs/decisions/0005-real-planner-adapter-http-client.md`](docs/decisions/0005-real-planner-adapter-http-client.md)
  for exactly what's assumed and what must be checked before production use.
- **`notify_approvers` should also fire from the app itself**: right now this
  bot only DMs approvers when *it* drives a transition into a pending stage.
  Once merged, `planner_api.py`'s transition endpoint should call this after
  *any* transition into `pending_l1`/`pending_l2` -- including ones triggered by
  the bell icon in the app -- so Slack approvals stay in sync regardless of
  where the quote was submitted from.
- **`MockPlannerAdapter` has no persistence** -- restarting the process resets
  all state. That's fine for local testing, obviously not for anything real.

## Merging into `emblaze`

Once you have repo/AWS access, per handbook 3.2's checklist:

1. Copy `slack_bot/` into the `emblaze` repo (e.g. as `slack_api/`, or flatten it
   into a single `slack_api.py` if that fits the existing code style better).
2. Re-verify `RealPlannerAdapter` in `planner_adapter.py` against the actual
   `planner_api.py` source (endpoint paths, request/response shapes) -- see the
   unverified caveat at the top of the class and
   `docs/decisions/0005-real-planner-adapter-http-client.md`. Since this code
   would then live in the same process as `planner_api.py`, prefer switching to
   direct function imports over HTTP calls to itself.
3. Swap `FakeSlackClient` for `SlackClient` in `app.py` (or just set
   `SLACK_CLIENT=real` and provide a real `SLACK_BOT_TOKEN`).
4. Register the blueprint from `routes.py` next to `planner_api`'s in the real
   `app.py`, and add both `/slack/commands` and `/slack/interactions` to
   `_PUBLIC_PATHS` (no browser session reaches these routes).
5. Add two secrets to AWS Secrets Manager: `emblaze-prod/slack-signing-secret`
   and `emblaze-prod/slack-bot-token` (use the repo's documented "add a secret"
   recipe in `CLAUDE.md`).
6. Add the new file(s) to the Dockerfile `COPY` list and `deploy.yml` paths --
   grep for `planner_api.py` and mirror every place it appears.
7. On the Slack side (api.slack.com/apps, all point-and-click): create the app,
   add the `/emblaze` slash command pointing at
   `https://emblaze.emtech.us/slack/commands`, turn on Interactivity pointing at
   `https://emblaze.emtech.us/slack/interactions`, grant `commands`,
   `chat:write`, `users:read`, `users:read.email` scopes, install to the
   workspace, copy the bot token + signing secret into the AWS secrets from
   step 5.
8. Follow the handbook's suggested build order (3.6) to verify each piece
   against the real backend: ping -> whoami -> status -> plan (both week- and
   day-mode) -> quote -> approvals -> reject. Checkpoint with Josh before
   secrets, first write, and approvals, per the handbook.

Guardrails already enforced in this code (3.7) -- keep them true after merging:
signature verified before anything else is read; unknown email always refused,
never a default user; role checked bot-side even though the transition endpoint
enforces it too; the bot never calls anything QuickBooks-related, `PUT /users`,
any `DELETE` endpoint, or a direct contract-registry write.

If this bot instead gets hosted standalone (handed to Russell per the
`starthere` contract) before repo access to `emblaze` arrives, see
[`docs/decisions/0003-build-to-starthere-contract-now.md`](docs/decisions/0003-build-to-starthere-contract-now.md)
for how that path and this one reconcile.

## Architecture decisions

Recorded in [`docs/decisions/`](docs/decisions/) as living ADRs (updated, never deleted, when a
decision changes):

| ADR | Decision |
|---|---|
| [0001](docs/decisions/0001-no-portal-sso-on-slack-routes.md) | Portal SSO is not wired in — this app's only routes are Slack webhooks authenticated by Slack's own signature. |
| [0002](docs/decisions/0002-no-independent-datastore.md) | No datastore of its own — all planner data lives in emblaze's existing DynamoDB table. |
| [0003](docs/decisions/0003-build-to-starthere-contract-now.md) | Build to the Emtech `starthere` contract now, independent of when `emblaze` repo access arrives. |
| [0004](docs/decisions/0004-day-based-plan-scheduling.md) | Day-based scheduling on the plan modal's technician line: shape decision (`scheduleUnit`/`activeDays`) and why. |
| [0005](docs/decisions/0005-real-planner-adapter-http-client.md) | `RealPlannerAdapter` is a real HTTP client, unverified against the real API pending repo access. |
| [0006](docs/decisions/0006-internal-teams-not-external-clients.md) | Quotes are for internal Emtech teams/departments, not external client companies — `client` renamed to `team` throughout. |

## Contacts

For a GitHub repo under `Emtech-LLC`, a Claude Code seat, getting this app
hosted, or any real credential it needs: **Russell Goodrick
(russellg@emtech.us)**. For questions about the Emblaze product/handbook
itself, see the handbook's own contacts (Josh, for checkpoint sign-off on
secrets/first-write/approvals).
