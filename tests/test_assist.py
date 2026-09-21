import json
import subprocess
import sys
from pathlib import Path

import pytest

from skydiscover.assist import JOB_SCHEMA, AssistError, _run, _validate_forwarded_args, load_job
from skydiscover.evaluation import subprocess_proxy


def _write_consumer_files(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "initial.py").write_text("value = 1\n", encoding="utf-8")
    (root / "config.yaml").write_text("max_iterations: 1\n", encoding="utf-8")
    (root / "evaluator.py").write_text(
        "from skydiscover.evaluation import EvaluationResult\n"
        "def evaluate(program_path):\n"
        "    print('consumer diagnostic')\n"
        "    return EvaluationResult(metrics={'combined_score': 0.75}, "
        "artifacts={'feedback': 'isolated'})\n",
        encoding="utf-8",
    )
    manifest = root / "job.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": JOB_SCHEMA,
                "consumer": "test-consumer",
                "working_directory": ".",
                "initial_program": "initial.py",
                "evaluator": "evaluator.py",
                "config": "config.yaml",
                "output": "output",
                "evaluator_command": [sys.executable],
                "evaluator_timeout_s": 30,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_check_probes_foreign_evaluator_without_installing_skydiscover(tmp_path: Path) -> None:
    manifest = _write_consumer_files(tmp_path / "consumer")

    process = subprocess.run(
        [sys.executable, "-m", "skydiscover.assist", "check", str(manifest)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert process.returncode == 0, process.stderr
    payload = json.loads(process.stdout)
    assert payload["status"] == "ok"
    assert payload["consumer"] == "test-consumer"
    assert payload["environment_boundary"] == "subprocess-json"


def test_proxy_returns_metrics_and_artifacts_from_foreign_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _write_consumer_files(tmp_path / "consumer")
    job = load_job(manifest)
    worker = Path(subprocess_proxy.__file__).with_name("subprocess_worker.py")
    candidate = tmp_path / "candidate.py"
    candidate.write_text("value = 2\n", encoding="utf-8")
    values = {
        "SKYDISCOVER_ASSIST_EVALUATOR_COMMAND": json.dumps(job.evaluator_command),
        "SKYDISCOVER_ASSIST_EVALUATOR": str(job.evaluator),
        "SKYDISCOVER_ASSIST_WORKER": str(worker),
        "SKYDISCOVER_ASSIST_WORKING_DIRECTORY": str(job.working_directory),
        "SKYDISCOVER_ASSIST_EVALUATOR_TIMEOUT_S": "30",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    result = subprocess_proxy.evaluate(str(candidate))

    assert result.metrics == {"combined_score": 0.75}
    assert result.artifacts == {"feedback": "isolated"}


def test_job_rejects_output_inside_skydiscover_checkout(tmp_path: Path) -> None:
    manifest = _write_consumer_files(tmp_path / "consumer")
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["output"] = str(Path(__file__).resolve().parents[1] / "forbidden-output")
    manifest.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(AssistError, match="outside the SkyDiscover checkout"):
        load_job(manifest)


@pytest.mark.parametrize("argument", ["--output", "-o", "--config=other.yaml", "-c"])
def test_forwarded_args_cannot_override_manifest_paths(argument: str) -> None:
    with pytest.raises(AssistError, match="owned by the assist manifest"):
        _validate_forwarded_args([argument])


def test_run_uses_relocated_evaluator_and_cli(tmp_path, monkeypatch):
    job = load_job(_write_consumer_files(tmp_path / "consumer"))
    calls = []

    def capture(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", capture)
    assert _run(job, []) == 0
    command, kwargs = calls[0]
    assert command[2] == "skydiscover.optimize.cli"
    assert Path(command[4]).is_file()
    assert Path(kwargs["env"]["SKYDISCOVER_ASSIST_WORKER"]).is_file()
