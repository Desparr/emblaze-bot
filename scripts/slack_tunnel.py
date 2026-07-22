#!/usr/bin/env python3
"""Launch the bot locally and expose it over a public HTTPS tunnel.

Usage:
    python3 scripts/slack_tunnel.py

The script starts the Flask app on port 8080, then starts either Cloudflare
Tunnel or ngrok if one is installed. Keep the process running while Slack is
pointed at the printed public URL.
"""

from __future__ import annotations

import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
APP_CMD = [
    str(ROOT / ".venv" / "bin" / "python3"),
    "-c",
    "from app import app; app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)",
]
APP_URL = "http://127.0.0.1:8080"


def _launch(command: list[str], *, name: str) -> subprocess.Popen[str]:
    return subprocess.Popen(command, cwd=ROOT, text=True)


def _pick_tunnel_command() -> tuple[str, list[str]]:
    cloudflared = shutil.which("cloudflared")
    if cloudflared:
        return "cloudflared", [cloudflared, "tunnel", "--url", APP_URL, "--no-autoupdate"]

    ngrok = shutil.which("ngrok")
    if ngrok:
        return "ngrok", [ngrok, "http", "8080"]

    raise RuntimeError(
        "No tunnel tool found. Install 'cloudflared' or 'ngrok', then rerun scripts/slack_tunnel.py."
    )


def _wait_for_healthz(timeout_seconds: int = 20) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            with urlopen(f"{APP_URL}/healthz", timeout=2) as response:
                if response.status == 200:
                    return
        except URLError as exc:
            last_error = exc
        time.sleep(0.5)

    raise RuntimeError(f"App did not become healthy at {APP_URL}/healthz") from last_error


def main() -> int:
    app_proc = _launch(APP_CMD, name="app")
    tunnel_name = None
    tunnel_proc = None

    def _shutdown(*_args):
        for proc in (tunnel_proc, app_proc):
            if proc and proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        _wait_for_healthz()
        tunnel_name, tunnel_command = _pick_tunnel_command()
        print(f"Started app on {APP_URL}")
        print(f"Launching {tunnel_name} tunnel...")
        tunnel_proc = _launch(tunnel_command, name=tunnel_name)
        print("Point Slack to the public URL shown by the tunnel process.")
        print("Press Ctrl+C to stop both processes.")

        while True:
            app_code = app_proc.poll()
            tunnel_code = tunnel_proc.poll() if tunnel_proc else None
            if app_code is not None:
                raise RuntimeError(f"App exited with code {app_code}")
            if tunnel_code is not None:
                raise RuntimeError(f"Tunnel exited with code {tunnel_code}")
            time.sleep(1)
    except Exception:
        _shutdown()
        raise
    except KeyboardInterrupt:
        _shutdown()
    finally:
        _shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())