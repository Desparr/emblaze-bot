"""Map a Slack user to their Emblaze account (handbook 2.4/3.2).

Signature verification proves "this request came from Slack"; this proves
"and it was Simon" -- together they replace the browser's session+CSRF. There
is no default/fallback identity: an email not in the allowlist gets refused (3.7).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("slack_bot.identity")


def resolve_identity(slack_user_id: str, slack_client, adapter) -> dict | None:
    email = slack_client.lookup_user_email(slack_user_id)
    if not email:
        logger.warning("could not resolve email for slack user %s", slack_user_id)
        return None

    users = adapter.get_users()
    record = users.get(email)
    if record is None:
        logger.info("slack user %s (%s) is not in the emblaze allowlist", slack_user_id, email)
        return None

    return {
        "email": email,
        "role": record["role"],
        "modules": record.get("modules"),
        "name": record.get("name", email),
    }
