# Emblaze Slack Bot -- guide for developers & AI agents

Implements Part 3 of the Emblaze Product Handbook: a Slack app (`/emblaze plan|quote|status|
whoami|ping`) that lets people create plans, quotes, and contracts without opening
`emblaze.emtech.us`. A thin Flask app; the only two functional routes are Slack webhooks
(`/slack/commands`, `/slack/interactions`), authenticated by Slack's own HMAC signature, not a
browser session. Built to the Emtech app-author contract (`Emtech-LLC/starthere`) so it can be
handed to Russell for hosting independent of the original "merge into emblaze" plan -- see
`docs/decisions/0003-build-to-starthere-contract-now.md`.

Humans read `README.md`. This file is for an agent working in this repo.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in local values; .env is gitignored
.venv/bin/python -m unittest discover -s tests
.venv/bin/python app.py         # http://localhost:8080 (PORT from .env, default 8080)

# Or via the container (mirrors production):
docker build -t emblaze-bot .
docker run --rm -p 8080:8080 --env-file .env emblaze-bot
curl -f http://localhost:8080/healthz    # expect 200
```

No real Slack app or `SLACK_BOT_TOKEN` is needed for local testing -- leave `SLACK_CLIENT=fake`
and `PLANNER_ADAPTER=mock`, and drive the whole bot with `scripts/sign_request.py` (see
README "Local test loop").

## Env vars & health path

- **Health endpoint:** `GET /healthz` (alias `/health`) returns 200, `{"ok": true, ...}`. Open,
  no auth, no downstream calls. Not yet hosted -- no live URL to poll today.
- **Config:** all config/secrets are read from environment variables; every one is listed
  (names, no values) in `.env.example`.

| Env var | What | Source |
|---|---|---|
| `PORT` | server port (default 8080) | set by platform in prod |
| `APP_ENV` | `dev` \| `prod` | non-secret |
| `SLACK_SIGNING_SECRET` | HMAC key for verifying Slack requests | Russell (Secrets Manager) once hosted |
| `SLACK_BOT_TOKEN` | Bot User OAuth token (`xoxb-...`) | Russell once hosted |
| `SLACK_CLIENT` | `fake` (offline, logs instead of calling slack.com) or `real` | you, locally |
| `SLACK_MAX_REQUEST_AGE_SECONDS` | replay-protection window, default 300 | non-secret |
| `PLANNER_ADAPTER` | `mock` (in-memory, seeded) or `real` (HTTP client, unverified -- see below) | you, locally |
| `EMBLAZE_BASE_URL` | only used once `PLANNER_ADAPTER=real` | non-secret |
| `PORTAL_SSO_*`, `AUTH_REQUIRE` | **not wired in** -- see `docs/decisions/0001-no-portal-sso-on-slack-routes.md` | n/a |

## Map

| Path | What |
|---|---|
| `app.py` | entrypoint: builds the Flask app, registers the blueprint, `/healthz` + `/health` |
| `slack_bot/routes.py` | the blueprint: `POST /slack/commands`, `POST /slack/interactions` |
| `slack_bot/verify.py` | Slack HMAC signature verification -- runs before anything else |
| `slack_bot/identity.py` | Slack user -> Emblaze account mapping; unknown email is refused, never a default user |
| `slack_bot/commands.py` | `/emblaze <ping\|whoami\|status\|plan\|quote>` dispatch |
| `slack_bot/interactions.py` | modal submits + Approve/Reject button clicks; parses week- or day-mode technician data |
| `slack_bot/planner_adapter.py` | the ONE seam to the Emblaze backend -- `MockPlannerAdapter` (in-memory) + `RealPlannerAdapter` (HTTP client, unverified -- see its docstring) |
| `slack_bot/approvals.py`, `blocks.py`, `math_utils.py` | approval DMs, Block Kit builders (incl. the day-picker), handbook 2.3 cost math (week- and day-mode) |
| `tests/` | unit tests -- signature verification, math, role rules, commands, interactions, identity, blocks, `RealPlannerAdapter`'s HTTP wiring |
| `scripts/sign_request.py` | signs a request the way Slack would, for local curl testing |
| `Dockerfile` | container image (base `public.ecr.aws/*`, binds `0.0.0.0:$PORT`) |
| `.env.example` | every env var this app reads (names, no values) |
| `docs/decisions/` | ADRs -- read before assuming this app should behave like a typical starthere app |

## Rules (important)
- **Never commit secrets.** Read them from environment variables; real values come from Russell once this is hosted.
- **Base image from `public.ecr.aws/*`** -- Docker Hub base images hit the pull-rate limit and break the CI build.
- **Server binds `0.0.0.0:${PORT}`** with `ENV PORT=8080` / `EXPOSE 8080`.
- **The health endpoint must return 200.** A deploy is not done until it is green.
- **Verify the Slack signature on every request, before reading anything else** (`verify.py`) -- this is this app's actual auth boundary, not portal SSO (see `docs/decisions/0001-...md`).
- **Unknown email -> refuse politely, never fall back to a default user** (`identity.py`).
- **Never touch QuickBooks, `PUT /users`, `DELETE` endpoints, or a direct contract-registry write** -- creating contracts only happens by winning a quote.
- **This app holds no datastore of its own** -- see `docs/decisions/0002-no-independent-datastore.md`.
- **Enforce LF** via `.gitattributes` -- a CRLF Dockerfile/script breaks the Linux CI build.
- **Never build the Docker image on Windows and upload it** -- build locally only to test.
- **Record decisions as ADRs** in `docs/decisions/` -- update Status/Consequences, never delete.
- **`RealPlannerAdapter` is unverified** -- its endpoint paths/shapes are a best-effort guess (see its docstring and `docs/decisions/0005-...md`). Do not remove that caveat comment; update it once someone actually checks it against real `planner_api.py` source.

## Gotchas (learned the hard way)
- **`PLANNER_ADAPTER=mock` resets on every restart.** It's in-memory, seeded fresh each run --
  don't expect state (plans, quotes) to survive a redeploy or even a local restart.
- **The git repo root is this directory (`emblaze-bot/`), not `slack_bot/`.** It used to be rooted
  one level down inside `slack_bot/`, which meant `app.py`, `tests/`, `README.md`, and this
  `Dockerfile` weren't version-controlled at all. Fixed 2026-07-14 -- if you ever see the repo
  root drift again, that's the bug to look for.
- **Day-mode plans are now supported from Slack (2026-07-21).** A prior attempt wrote
  `scheduleUnit: "day"` without collecting matching per-technician day data, which would have
  priced day-mode plans wrong -- that option was removed for v1 (see git history). It's been
  reintroduced properly: `blocks.py`'s plan modal has a `schedule_mode_block` + `days_block`
  (Mon-Sun checkboxes), `interactions.py` parses and validates whichever field matches the
  selected mode, and `math_utils.py`'s day-mode cost formula (`weekly_rate / 5` per day) was
  already correct and tested -- only the Slack-side collection was missing. See
  `docs/decisions/0004-day-based-plan-scheduling.md` for the full shape decision
  (`activeDays` = lowercase weekday abbreviations, stored per-technician alongside
  `scheduleUnit`) and why a per-technician day-picker was chosen over a calendar-date picker.
- **`RealPlannerAdapter` is a real HTTP client but its shapes are unverified.** It was written
  with no access to the real `emblaze` repo or a live API -- every `/api/planner/*` path and
  request/response shape in `planner_adapter.py` is a best-effort guess reshaped to match
  `MockPlannerAdapter`'s return shapes. Do not point `PLANNER_ADAPTER=real` at a production
  backend without a human checking it against the real `planner_api.py` source first --
  see the big caveat comment at the top of the `RealPlannerAdapter` class and
  `docs/decisions/0005-real-planner-adapter-http-client.md`.
- **The signing secret and bot token are real secrets in the local `.env`** (not a placeholder) --
  don't copy `.env` anywhere, and don't paste its contents into chat, a doc, or a commit.

<!-- Company operating manual (the contract, routing, playbooks): Emtech-LLC/starthere -> CLAUDE.md.
     For hosting handoff, a GitHub repo under Emtech-LLC, or a Claude Code seat: Russell Goodrick
     (russellg@emtech.us). gbrain footnote: this app does not use gbrain. -->
