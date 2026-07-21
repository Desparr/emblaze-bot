"""Thin wrapper over the Slack Web API.

Only the calls Part 3 actually needs: resolving identity (users.info /
users.lookupByEmail), opening modals (views.open), posting/updating messages
(chat.postMessage / chat.update), and replying via a response_url.
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger("slack_bot.slack_client")

SLACK_API_BASE = "https://slack.com/api"


class SlackApiError(Exception):
    def __init__(self, method: str, payload: dict):
        self.method = method
        self.payload = payload
        super().__init__(f"Slack API call {method} failed: {payload.get('error')}")


class SlackClient:
    def __init__(self, bot_token: str, *, base_url: str = SLACK_API_BASE, session: requests.Session | None = None):
        self.bot_token = bot_token
        self.base_url = base_url
        self.session = session or requests.Session()

    def _call(self, method: str, json_body: dict) -> dict:
        resp = self.session.post(
            f"{self.base_url}/{method}",
            json=json_body,
            headers={"Authorization": f"Bearer {self.bot_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise SlackApiError(method, data)
        return data

    def lookup_user_email(self, slack_user_id: str) -> str | None:
        """users.info -> profile.email. Requires the users:read.email scope (3.2)."""
        data = self._call("users.info", {"user": slack_user_id})
        email = data.get("user", {}).get("profile", {}).get("email")
        return email.lower() if email else None

    def lookup_user_id_by_email(self, email: str) -> str | None:
        """users.lookupByEmail -> Slack user id, used to DM approvers (3.5)."""
        try:
            data = self._call("users.lookupByEmail", {"email": email})
        except SlackApiError as exc:
            if exc.payload.get("error") == "users_not_found":
                return None
            raise
        return data.get("user", {}).get("id")

    def open_view(self, trigger_id: str, view: dict) -> dict:
        return self._call("views.open", {"trigger_id": trigger_id, "view": view})

    def push_view(self, trigger_id: str, view: dict) -> dict:
        """Stack a new modal on top of the current one (used for the reject-note modal)."""
        return self._call("views.push", {"trigger_id": trigger_id, "view": view})

    def post_message(self, channel: str, *, text: str, blocks: list | None = None) -> dict:
        body = {"channel": channel, "text": text}
        if blocks is not None:
            body["blocks"] = blocks
        return self._call("chat.postMessage", body)

    def update_message(self, channel: str, ts: str, *, text: str, blocks: list | None = None) -> dict:
        body = {"channel": channel, "ts": ts, "text": text}
        if blocks is not None:
            body["blocks"] = blocks
        return self._call("chat.update", body)

    def post_to_response_url(self, response_url: str, payload: dict) -> None:
        resp = self.session.post(response_url, json=payload, timeout=10)
        resp.raise_for_status()
