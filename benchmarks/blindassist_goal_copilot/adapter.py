"""Verify a BA SearchTaskBundle and emit a proposal-only mock CandidateBundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[1]
PROTOCOL_ID = "GOAL-COPILOT-1"
TASK_KIND = "blindassist.search_task_bundle"
CANDIDATE_KIND = "blindassist.candidate_bundle"
TASK_PAYLOADS = (
    "README.md",
    "initial_policy.py",
    "protocol.json",
    "public_scenarios/scenarios.json",
    "task_api.py",
)
CANDIDATE_PAYLOADS = (
    "candidate/policy.py",
    "candidate_manifest.json",
    "provenance.json",
    "search_metrics.json",
)


class BundleError(ValueError):
    """An input or output bundle violates the frozen bridge contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_checksums(directory: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {name: sha256(directory / Path(name)) for name in sorted(names)}


def content_id(checksums: dict[str, str]) -> str:
    return hashlib.sha256(canonical_json(checksums)).hexdigest()


def git_commit() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _file_members(directory: Path) -> set[str]:
    return {
        path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()
    }


def _verify_exact_members(directory: Path, allowed: set[str]) -> None:
    actual = _file_members(directory)
    if actual != allowed:
        raise BundleError(f"bundle members must be exactly {sorted(allowed)}; got {sorted(actual)}")


def verify_task_bundle(directory: Path) -> dict[str, Any]:
    _verify_exact_members(directory, {*TASK_PAYLOADS, "checksums.json", "manifest.json"})
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != TASK_KIND or manifest.get("protocol_id") != PROTOCOL_ID:
        raise BundleError("wrong SearchTaskBundle kind or protocol")
    if manifest.get("sealed_material_exported") is not False:
        raise BundleError("sealed evaluator material must not be exported")
    if manifest.get("search_authority") != "PROPOSAL_ONLY":
        raise BundleError("external search authority must remain proposal-only")
    recorded = json.loads((directory / "checksums.json").read_text(encoding="utf-8"))
    actual = payload_checksums(directory, TASK_PAYLOADS)
    if recorded != actual:
        raise BundleError("SearchTaskBundle payload checksum mismatch")
    bundle_id = content_id(actual)
    if manifest.get("bundle_digest") != bundle_id or directory.name != bundle_id:
        raise BundleError("SearchTaskBundle content identity mismatch")
    return manifest


def verify_candidate_bundle(directory: Path) -> dict[str, Any]:
    _verify_exact_members(directory, {*CANDIDATE_PAYLOADS, "checksums.json"})
    manifest = json.loads((directory / "candidate_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != CANDIDATE_KIND or manifest.get("protocol_id") != PROTOCOL_ID:
        raise BundleError("wrong CandidateBundle kind or protocol")
    if manifest.get("candidate_files") != ["candidate/policy.py"]:
        raise BundleError("candidate surface exceeds the policy allowlist")
    recorded = json.loads((directory / "checksums.json").read_text(encoding="utf-8"))
    actual = payload_checksums(directory, CANDIDATE_PAYLOADS)
    if recorded != actual:
        raise BundleError("CandidateBundle payload checksum mismatch")
    candidate_id = sha256(directory / "candidate/policy.py")
    if manifest.get("candidate_id") != candidate_id or directory.name != candidate_id:
        raise BundleError("CandidateBundle content identity mismatch")
    return manifest


def emit_mock_candidate(task_bundle: Path, output_root: Path) -> Path:
    task_manifest = verify_task_bundle(task_bundle)
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="goal-copilot-candidate-", dir=output_root))
    try:
        policy_path = staging / "candidate/policy.py"
        policy_path.parent.mkdir(parents=True)
        shutil.copy2(task_bundle / "initial_policy.py", policy_path)
        candidate_id = sha256(policy_path)
        provenance = {
            "source_search_task_bundle_digest": task_manifest["bundle_digest"],
            "skydiscover_repository_commit": git_commit(),
            "search_configuration": {
                "path": "benchmarks/blindassist_goal_copilot/config.yaml",
                "sha256": sha256(MODULE_DIR / "config.yaml"),
            },
            "parent_candidate": None,
            "generation": 0,
            "iteration": 0,
            "model_provider_identity": "none/mock",
            "resource_usage": {"model_calls": 0, "evaluation_calls": 0},
        }
        (staging / "provenance.json").write_bytes(canonical_json(provenance))
        (staging / "search_metrics.json").write_bytes(
            canonical_json(
                {
                    "authority": "PROVENANCE_ONLY_NOT_ACCEPTANCE",
                    "ranking_fitness": 0.0,
                    "note": "deterministic mock; no Sky evaluator or model call",
                }
            )
        )
        (staging / "candidate_manifest.json").write_bytes(
            canonical_json(
                {
                    "schema_version": 1,
                    "kind": CANDIDATE_KIND,
                    "protocol_id": PROTOCOL_ID,
                    "candidate_id": candidate_id,
                    "source_search_task_bundle_digest": task_manifest["bundle_digest"],
                    "candidate_files": ["candidate/policy.py"],
                    "proposal_authority": "SKYDISCOVER_ONLY",
                    "acceptance_authority": "BLINDASSIST_ONLY",
                }
            )
        )
        checksums = payload_checksums(staging, CANDIDATE_PAYLOADS)
        (staging / "checksums.json").write_bytes(canonical_json(checksums))
        destination = output_root / PROTOCOL_ID / task_manifest["bundle_digest"] / candidate_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if _file_members(staging) != _file_members(destination) or any(
                (staging / Path(name)).read_bytes() != (destination / Path(name)).read_bytes()
                for name in {*CANDIDATE_PAYLOADS, "checksums.json"}
            ):
                raise BundleError("existing candidate ID contains different bytes")
            shutil.rmtree(staging)
        else:
            os.replace(staging, destination)
        verify_candidate_bundle(destination)
        return destination
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--mock", action="store_true", help="Emit the deterministic zero-model candidate"
    )
    args = parser.parse_args()
    if not args.mock:
        parser.error("V0 supports only --mock; model search is not authorized")
    result = emit_mock_candidate(args.bundle.resolve(), args.output_root.resolve())
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
