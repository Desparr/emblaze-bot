import hashlib
import hmac
import time
import unittest

from slack_bot.verify import SignatureVerificationError, verify_slack_signature

SECRET = "test-signing-secret"


def sign(secret: str, timestamp: str, body: bytes) -> str:
    basestring = b"v0:" + timestamp.encode() + b":" + body
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


class VerifySlackSignatureTests(unittest.TestCase):
    def test_valid_signature_passes(self):
        timestamp = str(int(time.time()))
        body = b"command=/emblaze&text=ping"
        signature = sign(SECRET, timestamp, body)
        verify_slack_signature(SECRET, timestamp, body, signature)  # should not raise

    def test_wrong_secret_rejected(self):
        timestamp = str(int(time.time()))
        body = b"command=/emblaze&text=ping"
        signature = sign("a-different-secret", timestamp, body)
        with self.assertRaises(SignatureVerificationError):
            verify_slack_signature(SECRET, timestamp, body, signature)

    def test_tampered_body_rejected(self):
        timestamp = str(int(time.time()))
        signature = sign(SECRET, timestamp, b"command=/emblaze&text=ping")
        with self.assertRaises(SignatureVerificationError):
            verify_slack_signature(SECRET, timestamp, b"command=/emblaze&text=approve-everything", signature)

    def test_stale_timestamp_rejected(self):
        timestamp = str(int(time.time()) - 600)  # 10 minutes old
        body = b"command=/emblaze&text=ping"
        signature = sign(SECRET, timestamp, body)
        with self.assertRaises(SignatureVerificationError):
            verify_slack_signature(SECRET, timestamp, body, signature, max_age_seconds=300)

    def test_missing_headers_rejected(self):
        with self.assertRaises(SignatureVerificationError):
            verify_slack_signature(SECRET, "", b"body", "")


if __name__ == "__main__":
    unittest.main()
