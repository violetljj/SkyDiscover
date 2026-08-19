# L10M-DIAG-1: Objective x Reachability Audit

This post-hoc diagnostic audit freezes the L10M-ORACLE-3 evaluator and asks
whether its score responds to meaningful behavioral changes and whether the
current program surface can express such a change. It uses the consumed
`train` split and the 12 already adjudicated L10M-SKY-1 hidden instances. It
does not access fresh blind data or call a search model.

The audit compares the frozen baseline, a previously consumed instruction-only
shortcut, and a hand-written lower-alignment-threshold policy. The first is a
counterfactual objective probe: it changes instruction count without improving
task, safety, path, arrival, or reacquisition behavior. The second is a
reachability probe: it changes a policy threshold and is accepted only if the
evaluator attributes the gain to a substantive component.

## Frozen decision rules

- `objective_signal`: an instruction-only candidate must not be called a
  behavioral improvement; its substantive delta must be zero.
- `reachable_effect_signal`: a hand-written candidate must remain valid and safe,
  improve a substantive behavioral metric, and have substantive score share at
  least `0.5` on development. Across the 12 consumed-hidden instances, its mean
  substantive delta must exceed `0.005` and at least half the instances must
  pass the behavioral gate.
- `robust_safe_reachability`: every consumed-hidden instance must remain valid,
  successful, and safely terminated. A positive cohort average cannot override
  this hard requirement.
- `meaningful_effect`: `0.005`, retained for comparison with L10M-COMP-2 and
  L10M-SKY-1. This development audit does not establish a hidden adjudication
  claim.

The resulting claim ceiling is limited to the consumed ORACLE-3 development
split, consumed SKY-1 hidden cohort, and frozen evaluator revision. Post-hoc
hidden replay is diagnostic evidence, not a fresh confirmatory result. It is
not evidence of real-world BlindAssist safety, general search value, or
deployment readiness.

The completed post-hoc replay found objective sensitivity and a reachable
effect, but not robust safe reachability. The threshold probe passed the
behavioral gate on 10/12 instances and had mean substantive delta `+0.007483`,
while one instance timed out. The frozen conclusion is therefore
`OBJECTIVE_SIGNAL_PRESENT_ROBUST_REACHABILITY_NOT_ESTABLISHED`.

Run from the repository root:

```text
uv run python benchmarks/blindassist_last10m_diag_1/run.py
```
