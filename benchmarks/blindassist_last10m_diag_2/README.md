# L10M-DIAG-2: Temporal Representation Audit

L10M-DIAG-2 is a bounded post-hoc diagnostic over the consumed L10M-ORACLE-3
development split and the consumed 12-instance L10M-SKY-1 hidden cohort. It
does not use fresh blind data or make search calls. The evaluator, cohort, and
hard safety gate remain unchanged.

## Diagnosis

The DIAG-1 policy timed out on `instance_07_H_08` because its first
target-directed action at node `turn` was `VEER_LEFT`. That action was safe but
had no transition and produced no progress. The policy stored no progress
contract, so it repeated `VEER_LEFT` until the 14-step episode budget expired.
This is a repeated local replanning failure with an incomplete termination
contract, not an evaluator timeout or a hidden temporal-state deadlock.

DIAG-2 records step-level traces for the old and new policies. The new policy
detects the failed move at the same observed progress level, excludes it from a
bounded set of observable alternatives, and selects `FORWARD`. The episode then
reaches `ARRIVED` without changing the evaluator or scenario.

## Candidate representation

The candidate exposes independently editable units for:

- `safety_contract`: mandatory non-motion fallback;
- `tracking_contract`: verification, temporal memory, and bounded reacquisition;
- `propose_moves`: ordered actions derived only from current observations;
- `progress_contract`: finite failed-action memory at one progress level;
- `decide`: state-machine composition and explicit terminal fallback.

These functions are a candidate-language prototype, not evidence that any
searcher can discover the policy. Search value must be tested separately after
this representation is frozen.

## Frozen result

The structured policy passes the behavioral gate on 11/12 consumed instances,
has mean substantive score delta `+0.013542`, and reaches `12/12 robust-safe`.
The DIAG-2 success rules are therefore met within the post-hoc consumed-data
claim ceiling. This establishes robust reachability in this diagnostic cohort;
it does not establish real-world safety, generality, or automated search value.

Run from the repository root:

```text
uv run python benchmarks/blindassist_last10m_diag_2/run.py
```
