"""Detached-worktree and execution-lock integrity checks for COMPONENT-2."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_PATH = HERE / "protocol.json"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


def snapshot() -> dict[str, Any]:
    head = _git("rev-parse", "HEAD").stdout.strip()
    tree = _git("rev-parse", "HEAD^{tree}").stdout.strip()
    branch = _git("symbolic-ref", "-q", "HEAD", check=False)
    tracked_status = _git("status", "--porcelain=v1", "--untracked-files=no").stdout
    return {
        "worktree": ROOT.resolve().as_posix(),
        "head": head,
        "tracked_tree": tree,
        "detached": branch.returncode != 0,
        "tracked_clean": tracked_status == "",
        "tracked_status": tracked_status,
    }


def verify(lock_path: Path, output_root: Path, phase: str) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if protocol["status"] != "EXECUTION_PROTOCOL_FROZEN":
        raise RuntimeError("formal execution blocked: protocol is not frozen")
    lock_path = lock_path.resolve()
    if not lock_path.is_file():
        raise RuntimeError(f"formal execution lock is missing: {lock_path}")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    current = snapshot()
    checks = {
        "experiment": lock.get("experiment_id") == protocol["experiment_id"],
        "worktree": Path(lock.get("worktree", "")).resolve() == ROOT.resolve(),
        "output_root": Path(lock.get("output_root", "")).resolve() == output_root.resolve(),
        "detached": current["detached"],
        "head": current["head"] == lock.get("frozen_head"),
        "tracked_tree": current["tracked_tree"] == lock.get("frozen_tracked_tree"),
        "tracked_clean": current["tracked_clean"],
        "owner_token": bool(lock.get("exclusive_owner_token")),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"fail-closed checkout drift at {phase}: {', '.join(failed)}")
    return {"phase": phase, "checks": checks, **current}
