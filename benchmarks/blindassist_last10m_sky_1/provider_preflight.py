#!/usr/bin/env python3
"""Freeze the executable Codex CLI identity used by L10M-SKY-1."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "provider_preflight.json"


def _run(*args: str) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=30)
    return (result.stdout or result.stderr).strip()


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to replace {OUTPUT}")
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("codex executable not found")
    version = _run(executable, "--version")
    login = _run(executable, "login", "status")
    if version.lower() == "unknown" or "logged in" not in login.lower():
        raise RuntimeError("Codex provider identity or login is not executable")
    payload = {
        "experiment_id": "L10M-SKY-1",
        "codex_executable": str(Path(executable).resolve()),
        "codex_version": version,
        "login_status": login,
        "status": "PASS",
    }
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
