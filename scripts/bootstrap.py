#!/usr/bin/env python3
"""Create or refresh the local virtualenv and install dependencies.

This script is safe to rerun after moving the repository. If the existing
`.venv` points at a different checkout, it is deleted and rebuilt.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, cwd=ROOT)


def _venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python3"


def _venv_is_valid() -> bool:
    python = _venv_python()
    pip = VENV_DIR / ("Scripts" if sys.platform == "win32" else "bin") / (
        "pip.exe" if sys.platform == "win32" else "pip"
    )

    if not python.exists() or not pip.exists():
        return False

    try:
        first_line = pip.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
    except (FileNotFoundError, IndexError):
        return False

    return str(VENV_DIR.resolve()) in first_line


def main() -> int:
    if not REQUIREMENTS.exists():
        raise FileNotFoundError(f"Missing requirements file: {REQUIREMENTS}")

    if VENV_DIR.exists() and not _venv_is_valid():
        shutil.rmtree(VENV_DIR)

    if not _venv_is_valid():
        _run([sys.executable, "-m", "venv", str(VENV_DIR)])

    _run([str(_venv_python()), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    print(f"Virtualenv ready at {VENV_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())