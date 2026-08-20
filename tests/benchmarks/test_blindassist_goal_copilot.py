from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pytest

ADAPTER_PATH = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "blindassist_goal_copilot" / "adapter.py"
)
SPEC = importlib.util.spec_from_file_location("blindassist_goal_copilot_adapter", ADAPTER_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def _task_bundle(root: Path) -> Path:
    staging = root / "task-staging"
    (staging / "public_scenarios").mkdir(parents=True)
    payload = {
        "README.md": b"public task\n",
        "initial_policy.py": b"def placeholder():\n    return None\n",
        "protocol.json": b"{}\n",
        "public_scenarios/scenarios.json": b"{}\n",
        "task_api.py": b"# typed API\n",
    }
    for name, value in payload.items():
        (staging / Path(name)).write_bytes(value)
    checksums = adapter.payload_checksums(staging, adapter.TASK_PAYLOADS)
    bundle_id = adapter.content_id(checksums)
    (staging / "checksums.json").write_bytes(adapter.canonical_json(checksums))
    (staging / "manifest.json").write_bytes(
        adapter.canonical_json(
            {
                "schema_version": 1,
                "kind": adapter.TASK_KIND,
                "protocol_id": adapter.PROTOCOL_ID,
                "source_repository": "violetljj/blind-assist",
                "source_commit": "a" * 40,
                "bundle_digest": bundle_id,
                "search_authority": "PROPOSAL_ONLY",
                "acceptance_authority": "BLINDASSIST_ONLY",
                "sealed_material_exported": False,
            }
        )
    )
    destination = root / bundle_id
    staging.rename(destination)
    return destination


def test_mock_candidate_is_deterministic_complete_and_proposal_only() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        bundle = _task_bundle(root)
        first = adapter.emit_mock_candidate(bundle, root / "outputs")
        first_bytes = {
            name: (first / Path(name)).read_bytes()
            for name in {*adapter.CANDIDATE_PAYLOADS, "checksums.json"}
        }
        second = adapter.emit_mock_candidate(bundle, root / "outputs")
        assert first == second
        assert first_bytes == {
            name: (second / Path(name)).read_bytes()
            for name in {*adapter.CANDIDATE_PAYLOADS, "checksums.json"}
        }
        manifest = adapter.verify_candidate_bundle(first)
        assert manifest["proposal_authority"] == "SKYDISCOVER_ONLY"
        assert manifest["acceptance_authority"] == "BLINDASSIST_ONLY"
        assert manifest["source_search_task_bundle_digest"] == bundle.name
        members = {path.name for path in first.rglob("*") if path.is_file()}
        assert "evaluator.py" not in members
        assert "sealed_scenarios.json" not in members


def test_modified_or_authority_leaking_task_bundle_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        bundle = _task_bundle(root)
        with (bundle / "initial_policy.py").open("a", encoding="utf-8") as stream:
            stream.write("# modified\n")
        with pytest.raises(adapter.BundleError, match="checksum"):
            adapter.emit_mock_candidate(bundle, root / "outputs")

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        bundle = _task_bundle(root)
        (bundle / "evaluator.py").write_text("# forbidden\n", encoding="utf-8")
        with pytest.raises(adapter.BundleError, match="members"):
            adapter.emit_mock_candidate(bundle, root / "outputs")
