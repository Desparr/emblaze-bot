"""Slack request signature verification.

Handbook 3.3: Slack signs every request with
    X-Slack-Signature:         v0=HMAC_SHA256(signing_secret, "v0:" + timestamp + ":" + raw_body)
    X-Slack-Request-Timestamp: unix seconds (reject if older than 5 minutes -- replay protection)

Guardrail 3.7: verify the signature on every request, before reading anything else.
This must run against the exact raw bytes Slack sent -- never against a re-serialized
or re-parsed body, or the HMAC will silently never match.
"""

import hashlib
import hmac
import time


class SignatureVerificationError(Exception):
    """Raised when a request cannot be verified as genuinely from Slack."""


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    raw_body: bytes,
    signature: str,
    *,
    max_age_seconds: int = 300,
) -> None:
    if not signing_secret:
        raise SignatureVerificationError("no signing secret configured")
    if not timestamp or not signature:
        raise SignatureVerificationError("missing X-Slack-Signature / X-Slack-Request-Timestamp header")

    try:
        request_time = int(timestamp)
    except ValueError:
        raise SignatureVerificationError("malformed timestamp header")

    if abs(time.time() - request_time) > max_age_seconds:
        raise SignatureVerificationError("stale request timestamp (possible replay)")

    basestring = b"v0:" + timestamp.encode() + b":" + raw_body
    digest = hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    computed_signature = f"v0={digest}"

    if not hmac.compare_digest(computed_signature, signature):
        raise SignatureVerificationError("signature mismatch")
