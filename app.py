"""Standalone entrypoint. Runs the Emblaze Slack bot on its own, with no
dependency on the real emblaze repo -- see README.md for the local test loop
and for what changes once you merge this into github.com/Emtech-LLC/emblaze.

In production this app is built to the Emtech app-author contract
(Emtech-LLC/starthere) and run under gunicorn per the Dockerfile, e.g.
`gunicorn -b 0.0.0.0:${PORT} app:app` -- app.run() below is for local dev
only, never the container entrypoint.
"""

import logging

from flask import Flask

from slack_bot.config import Config
from slack_bot.fake_slack_client import FakeSlackClient
from slack_bot.planner_adapter import build_adapter
from slack_bot.routes import create_slack_blueprint
from slack_bot.slack_client import SlackClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def build_slack_client():
    if Config.SLACK_CLIENT == "fake":
        return FakeSlackClient()
    return SlackClient(Config.SLACK_BOT_TOKEN)


def create_app() -> Flask:
    Config.validate()

    app = Flask(__name__)
    slack_client = build_slack_client()
    adapter = build_adapter(Config.PLANNER_ADAPTER, base_url=Config.EMBLAZE_BASE_URL)

    blueprint = create_slack_blueprint(
        signing_secret=Config.SLACK_SIGNING_SECRET,
        slack_client=slack_client,
        adapter=adapter,
        max_request_age_seconds=Config.SLACK_MAX_REQUEST_AGE_SECONDS,
    )
    app.register_blueprint(blueprint)

    # Health contract (starthere/building/containerizing.md): open, cheap,
    # data-free, no auth -- the deploy poller and Cloudflare tunnel curl this
    # after every deploy and treat non-200 as a failed rollout. Answer on both
    # paths, matching the emblaze reference app.
    @app.get("/healthz")
    @app.get("/health")
    def healthz():
        return {"ok": True, "plannerAdapter": Config.PLANNER_ADAPTER, "slackClient": Config.SLACK_CLIENT}

    return app


app = create_app()

if __name__ == "__main__":
    # Local dev server only. Bind 0.0.0.0 and read $PORT so this matches the
    # container's runtime contract; production uses gunicorn (see Dockerfile).
    app.run(host="0.0.0.0", port=Config.PORT, debug=True)
