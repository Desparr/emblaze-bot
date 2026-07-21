"""The Flask blueprint: POST /slack/commands and POST /slack/interactions.

When merging into github.com/Emtech-LLC/emblaze (handbook 3.2), register this
blueprint next to planner_api's, add both paths to app.py's _PUBLIC_PATHS (no
browser session reaches this file), and mirror slack_api.py into the Dockerfile
COPY list and deploy.yml wherever planner_api.py appears.
"""

import json
import logging

from flask import Blueprint, jsonify, request

from .commands import handle_slash_command
from .interactions import dispatch_interaction
from .verify import SignatureVerificationError, verify_slack_signature

logger = logging.getLogger("slack_bot.routes")


def create_slack_blueprint(*, signing_secret: str, slack_client, adapter, max_request_age_seconds: int = 300) -> Blueprint:
    bp = Blueprint("slack", __name__)

    def _verify_request() -> None:
        """Guardrail 3.7: verify the signature on every request, before reading
        anything else. Must run against the raw bytes Slack sent -- request.form
        or json.loads may re-encode differently and silently break the HMAC.
        """
        raw_body = request.get_data()
        verify_slack_signature(
            signing_secret,
            request.headers.get("X-Slack-Request-Timestamp", ""),
            raw_body,
            request.headers.get("X-Slack-Signature", ""),
            max_age_seconds=max_request_age_seconds,
        )

    @bp.route("/slack/commands", methods=["POST"])
    def slack_commands():
        try:
            _verify_request()
        except SignatureVerificationError as exc:
            logger.warning("rejected /slack/commands: %s", exc)
            return "invalid signature", 401

        payload = request.form.to_dict()
        logger.info("slash command from %s: %s", payload.get("user_id"), payload.get("text"))

        try:
            response_body = handle_slash_command(payload, slack_client, adapter)
        except Exception:
            logger.exception("error handling slash command")
            return jsonify({"response_type": "ephemeral", "text": "Something went wrong -- check the bot's logs."})

        return jsonify(response_body)

    @bp.route("/slack/interactions", methods=["POST"])
    def slack_interactions():
        try:
            _verify_request()
        except SignatureVerificationError as exc:
            logger.warning("rejected /slack/interactions: %s", exc)
            return "invalid signature", 401

        payload = json.loads(request.form["payload"])
        logger.info("interaction from %s: %s", payload.get("user", {}).get("id"), payload.get("type"))

        try:
            response_body = dispatch_interaction(payload, slack_client, adapter)
        except Exception:
            logger.exception("error handling interaction")
            return "", 200

        return jsonify(response_body)

    return bp
