# Consumer assist bridge

`skydiscover-assist` lets another repository use SkyDiscover as a temporary
auxiliary search tool without installing either project's dependencies into the
other. SkyDiscover runs in its own `uv` environment. The consumer evaluator runs
under a consumer-owned Python launcher and exchanges metrics and artifacts over
a one-document JSON subprocess protocol.

## Job manifest

Paths are resolved relative to the manifest. Output must be outside the
SkyDiscover checkout.

```json
{
  "schema": "skydiscover-assist-job-v1",
  "consumer": "blindassist",
  "working_directory": "../..",
  "initial_program": "research/active/example/initial_program.py",
  "evaluator": "research/active/example/evaluator.py",
  "config": "research/active/example/config.yaml",
  "output": "artifacts.local/evidence/example/skydiscover-search",
  "evaluator_command": ["E:/path/to/consumer-python-launcher.cmd"],
  "evaluator_timeout_s": 300
}
```

The evaluator must expose `evaluate(program_path)`. It may return a numeric
dictionary or an `EvaluationResult` with numeric `metrics` and JSON-compatible
`artifacts`. A compatibility-only `skydiscover.evaluation.EvaluationResult` is
provided inside the consumer process, so SkyDiscover does not need to be
installed there.

## Check and run

From the SkyDiscover checkout:

```powershell
uv run skydiscover-assist check E:\consumer\job.json
uv run skydiscover-assist run E:\consumer\job.json
```

`check` performs a zero-model-call transport probe: it resolves every path and
imports the evaluator using the declared consumer launcher. `run` repeats that
probe and then starts normal SkyDiscover search. Arguments after `--` are passed
to `skydiscover-run`, for example `-- --iterations 2`.

The bridge is deliberately not a daemon or package dependency. Removing the
consumer manifest and launcher stops the relationship; ordinary SkyDiscover
commands remain unchanged.
