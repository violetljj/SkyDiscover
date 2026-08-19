"""Local controller client for the persistent COMPONENT-2 remote evaluator."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any


class RemoteEvaluationError(RuntimeError):
    """A remote dispatch failed or became in-doubt."""


class RemoteEvaluationClient:
    def __init__(self, manifest_path: Path | dict[str, Any], journal_root: Path, worker_id: str):
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(manifest_path, Path)
            else manifest_path
        )
        self.manifest = manifest
        self.journal_root = journal_root / worker_id
        self.journal_root.mkdir(parents=True, exist_ok=True)
        self.worker_id = worker_id
        self.process: subprocess.Popen[str] | None = None

    def _command(self) -> list[str]:
        target = self.manifest["endpoint"]
        port = str(self.manifest["port"])
        python = f"{self.manifest['venv_dir']}/bin/python"
        script = f"{self.manifest['source_dir']}/benchmarks/blindassist_last10m_struct_component_2/remote_worker.py"
        return [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-p",
            port,
            target,
            python,
            "-u",
            script,
            "--worker-id",
            self.worker_id,
        ]

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self.process is not None and self.process.poll() is None:
            return self.process
        log = self.journal_root / "worker.stderr.log"
        stderr = log.open("a", encoding="utf-8", newline="\n")
        try:
            self.process = subprocess.Popen(
                self._command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                bufsize=1,
                encoding="utf-8",
            )
        except Exception:
            stderr.close()
            raise
        return self.process

    def evaluate(
        self,
        *,
        candidate_source: str,
        scenarios: list[dict[str, Any]],
        arm: str,
        mode: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        request_id = request_id or secrets.token_hex(16)
        request = {
            "request_id": request_id,
            "candidate_source": candidate_source,
            "candidate_sha256": hashlib.sha256(candidate_source.encode("utf-8")).hexdigest(),
            "scenarios": scenarios,
            "arm": arm,
            "mode": mode,
            "worker_id": self.worker_id,
            "dispatched_at_unix": time.time(),
        }
        before = self.journal_root / f"{request_id}.before.json"
        after = self.journal_root / f"{request_id}.after.json"
        try:
            with before.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(request, handle, sort_keys=True)
                handle.write("\n")
            process = self._ensure_process()
            if process.stdin is None or process.stdout is None:
                raise RemoteEvaluationError("remote worker pipes are unavailable")
            process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                raise RemoteEvaluationError("remote worker channel ended before response")
            response = json.loads(line)
            if response.get("request_id") != request_id:
                raise RemoteEvaluationError("remote response request id mismatch")
            if response.get("status") != "COMPLETED":
                raise RemoteEvaluationError(response.get("error", "remote evaluator failure"))
            with after.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(response, handle, sort_keys=True)
                handle.write("\n")
            return response["result"]
        except Exception as exc:
            in_doubt = self.journal_root / f"{request_id}.in_doubt.json"
            if not in_doubt.exists():
                with in_doubt.open("x", encoding="utf-8", newline="\n") as handle:
                    json.dump(
                        {
                            "request_id": request_id,
                            "status": "IN_DOUBT",
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                        handle,
                        sort_keys=True,
                    )
                    handle.write("\n")
            raise RemoteEvaluationError(f"dispatch {request_id} is in_doubt: {exc}") from exc

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            if self.process.stdin is not None:
                self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=30)
        self.process = None
