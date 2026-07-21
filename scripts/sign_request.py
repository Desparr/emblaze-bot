#!/usr/bin/env python3
"""Generate a validly-signed curl command for POST /slack/commands or
/slack/interactions -- lets you test signature verification and the whole
request flow locally with no real Slack workspace registered yet (handbook 3.3
done in reverse).

Examples:
  python scripts/sign_request.py commands --text ping --user-id U_SIMON
  python scripts/sign_request.py commands --text "quote" --user-id U_SIMON
  python scripts/sign_request.py interactions --payload-file my_click.json
  python scripts/sign_request.py raw --body 'command=/emblaze&text=ping&user_id=U_SIMON'

--secret must match SLACK_SIGNING_SECRET in your .env, or the bot will reject
the request with 401.
"""

import argparse
import hashlib
import hmac
import os
import shlex
import time
import urllib.parse

DEFAULT_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "test-signing-secret")
DEFAULT_BASE_URL = os.environ.get("BOT_BASE_URL", "http://localhost:3000")


def sign(secret: str, timestamp: str, body: bytes) -> str:
    basestring = b"v0:" + timestamp.encode() + b":" + body
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def print_curl(url: str, body: str, secret: str) -> None:
    timestamp = str(int(time.time()))
    signature = sign(secret, timestamp, body.encode())
    cmd = [
        "curl", "-s", "-X", "POST", url,
        "-H", "Content-Type: application/x-www-form-urlencoded",
        "-H", f"X-Slack-Request-Timestamp: {timestamp}",
        "-H", f"X-Slack-Signature: {signature}",
        "--data-raw", body,
    ]
    print(" ".join(shlex.quote(part) for part in cmd))


def build_commands_body(args: argparse.Namespace) -> str:
    fields = {
        "command": "/emblaze",
        "text": args.text,
        "user_id": args.user_id,
        "channel_id": args.channel_id,
        "trigger_id": args.trigger_id,
        "response_url": args.response_url,
    }
    return urllib.parse.urlencode(fields)


def build_interactions_body(args: argparse.Namespace) -> str:
    if args.payload_file:
        with open(args.payload_file) as fh:
            payload_json = fh.read()
    else:
        payload_json = args.payload
    return urllib.parse.urlencode({"payload": payload_json})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--secret", default=DEFAULT_SIGNING_SECRET, help="must match SLACK_SIGNING_SECRET in .env")
    parser.add_argument("--url", default=None, help="overrides the default per-subcommand URL")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_cmd = sub.add_parser("commands", help="sign a POST /slack/commands body")
    p_cmd.add_argument("--text", default="ping", help="e.g. 'ping', 'whoami', 'status', 'plan', 'quote'")
    p_cmd.add_argument("--user-id", default="U_SIMON", help="a key from FAKE_SLACK_USERS when SLACK_CLIENT=fake")
    p_cmd.add_argument("--channel-id", default="C_TEST")
    p_cmd.add_argument("--trigger-id", default="fake-trigger-id")
    p_cmd.add_argument("--response-url", default="https://example.com/response-url")

    p_int = sub.add_parser("interactions", help="sign a POST /slack/interactions body")
    p_int.add_argument("--payload", help="raw JSON string")
    p_int.add_argument("--payload-file", help="path to a JSON file containing the interaction payload")

    p_raw = sub.add_parser("raw", help="sign an arbitrary raw body")
    p_raw.add_argument("--body", required=True)

    args = parser.parse_args()

    if args.mode == "commands":
        body = build_commands_body(args)
        url = args.url or f"{DEFAULT_BASE_URL}/slack/commands"
    elif args.mode == "interactions":
        if not args.payload and not args.payload_file:
            parser.error("interactions needs --payload or --payload-file")
        body = build_interactions_body(args)
        url = args.url or f"{DEFAULT_BASE_URL}/slack/interactions"
    else:
        body = args.body
        url = args.url or DEFAULT_BASE_URL

    print_curl(url, body, args.secret)


if __name__ == "__main__":
    main()
