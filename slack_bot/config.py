import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    # Platform contract (starthere/building/containerizing.md): the container
    # listens on 0.0.0.0:$PORT: keep this at 8080 in production. Local `python
    # app.py` runs also read it so the port story is identical everywhere.
    PORT = int(os.environ.get("PORT", "8080"))
    APP_ENV = os.environ.get("APP_ENV", "dev")

    SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
    PLANNER_ADAPTER = os.environ.get("PLANNER_ADAPTER", "mock")
    # "fake" never calls slack.com -- it logs what it would have sent. Lets the
    # whole bot run and be curl-tested with no real Slack app registered yet.
    SLACK_CLIENT = os.environ.get("SLACK_CLIENT", "fake")
    EMBLAZE_BASE_URL = os.environ.get("EMBLAZE_BASE_URL", "https://emblaze.emtech.us")
    SLACK_MAX_REQUEST_AGE_SECONDS = int(os.environ.get("SLACK_MAX_REQUEST_AGE_SECONDS", "300"))

    @classmethod
    def validate(cls):
        if cls.SLACK_CLIENT == "real" and not cls.SLACK_BOT_TOKEN:
            raise RuntimeError("SLACK_CLIENT=real requires SLACK_BOT_TOKEN. Copy .env.example to .env and fill it in.")
        if not cls.SLACK_SIGNING_SECRET:
            raise RuntimeError(
                "Missing SLACK_SIGNING_SECRET. Copy .env.example to .env and set it -- any string works for "
                "local testing as long as scripts/sign_request.py signs with the same value."
            )
