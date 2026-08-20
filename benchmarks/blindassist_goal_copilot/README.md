# BlindAssist Goal Copilot bridge adapter

This directory is deliberately an adapter, not a benchmark authority. BlindAssist owns
`GOAL-COPILOT-1`, the hidden scenarios, evaluator, safety constraints, acceptance gate,
and claims. SkyDiscover may verify a frozen public `SearchTaskBundle` and propose a
`CandidateBundle`; it cannot accept a candidate or produce a BlindAssist verdict.

The first version is a deterministic zero-model dry-run. It copies the exported baseline
policy into a candidate, records source repository/commit/bundle provenance, and emits a
content-addressed package. It neither embeds nor calls a BA evaluator.

```powershell
uv run python benchmarks/blindassist_goal_copilot/adapter.py `
  --bundle E:/linnan/linnan/artifacts.local/sky_exports/GOAL-COPILOT-1/<sha256> `
  --output-root outputs/goal-copilot-bridge --mock
```

BlindAssist must then import and independently validate that proposal through its own
stable bridge command. Re-running this adapter for the same input yields the same
candidate identity. The claim ceiling is bridge mechanics only: no model was called and
no scientific or product result is established.

