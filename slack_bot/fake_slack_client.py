"""A stand-in for SlackClient that never talks to slack.com -- it just logs what
it would have sent. Lets you exercise the whole request/response flow (signature
verification, identity mapping, modal building, approval math) without a real
Slack app or bot token. Swap to the real SlackClient once you've registered the
Slack app (handbook 3.2) and want to see modals for real.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("slack_bot.fake_slack_client")

# Matches MockPlannerAdapter's seeded users so a local end-to-end run has a
# consistent story: these are the "Slack users" behind /slack/commands calls.
FAKE_SLACK_USERS = {
    "U_SIMON": "simonn@emtech.us",
    "U_JOSH": "josh@emtech.us",
    "U_PRIYA": "priya@emtech.us",
    "U_ALEX": "alex@emtech.us",
    "U_DESMOND": "desmondp@emtech.us",
    "U_MATTJ": "mattj@emtech.us",
}


class FakeSlackClient:
    def __init__(self):
        self.sent_messages = []
        self.opened_views = []
        self.updated_messages = []

    def lookup_user_email(self, slack_user_id: str):
        return FAKE_SLACK_USERS.get(slack_user_id)

    def lookup_user_id_by_email(self, email: str):
        for user_id, mapped_email in FAKE_SLACK_USERS.items():
            if mapped_email == email:
                return user_id
        return None

    def open_view(self, trigger_id: str, view: dict) -> dict:
        logger.info("[fake] views.open(trigger_id=%s):\n%s", trigger_id, json.dumps(view, indent=2))
        self.opened_views.append(view)
        return {"ok": True, "view": {**view, "id": "V_FAKE"}}

    def push_view(self, trigger_id: str, view: dict) -> dict:
        logger.info("[fake] views.push(trigger_id=%s):\n%s", trigger_id, json.dumps(view, indent=2))
        self.opened_views.append(view)
        return {"ok": True, "view": {**view, "id": "V_FAKE"}}

    def post_message(self, channel: str, *, text: str, blocks: list | None = None) -> dict:
        logger.info("[fake] chat.postMessage(channel=%s): %s", channel, text)
        entry = {"channel": channel, "text": text, "blocks": blocks, "ts": f"fake-{len(self.sent_messages)}"}
        self.sent_messages.append(entry)
        return {"ok": True, "channel": channel, "ts": entry["ts"]}

    def update_message(self, channel: str, ts: str, *, text: str, blocks: list | None = None) -> dict:
        logger.info("[fake] chat.update(channel=%s, ts=%s): %s", channel, ts, text)
        self.updated_messages.append({"channel": channel, "ts": ts, "text": text, "blocks": blocks})
        return {"ok": True, "channel": channel, "ts": ts}

    def post_to_response_url(self, response_url: str, payload: dict) -> None:
        logger.info("[fake] POST %s: %s", response_url, json.dumps(payload))
