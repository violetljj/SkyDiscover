# BlindAssist L10 Perception Policy 1

This is the new search boundary for the last-ten-metre route. It does not use
OCR text as the target oracle and does not expose `target_visible`, an identity
confidence invented by the evaluator, a correct next action, or graph topology.
The candidate sees only the output contract of BlindAssist perception and its
temporal entrance belief:

- `SEARCH`, `SET_VALUED`, `COMMIT`, or `REACQUIRE`;
- current candidate track IDs, normalized geometry, and non-OCR support edges;
- selected track, persistence, loss, bearing, and apparent scale change;
- an evaluator-owned approach-safety veto and terminal handoff flag.

The searchable policy chooses `SWEEP`, `CENTER_AND_APPROACH`, `HOLD`, `TRACK`,
`SCAN_LAST_BEARING`, or `ARRIVED`. A wrong/ungrounded `TRACK`, unsafe approach,
or invalid `ARRIVED` is a hard failure. AdaEvolve keeps a Pareto front over task
success, commit precision, truth retention, reacquisition, and instruction
count instead of hiding every trade-off in one scalar.

## Data authority

Checked-in episodes are explicitly marked `MECHANICS_FIXTURE`. They verify the
contract and evaluator only; they are not algorithm evidence and must not be
reported as real perception success. Scientific use starts only after replacing
them with frozen `BLINDASSIST_REAL_PERCEPTION` exports whose nodes contain:

1. support-ray proposal and temporal-belief outputs produced from real ordered
   images without evaluator truth in the candidate-visible fields;
2. separately frozen portal truth used only by evaluator-private fields;
3. source, model, protocol, and backend-receipt hashes in the episode manifest;
4. an honest transition authority. Ordered images without commanded pose may
   be labelled only as a proxy transition, never active-view causality.

This benchmark optimizes the policy after perception. It does not search model
weights, proposal thresholds, OCR rules, tracking parameters, or safety logic.
It cannot establish outside-to-entrance navigation, public accessibility,
metric distance, user benefit, or safety.

## Focused replay

```powershell
python benchmarks/blindassist_last10m_perception_1/evaluator/evaluator.py `
  benchmarks/blindassist_last10m_perception_1/initial_program.py train
python benchmarks/blindassist_last10m_perception_1/evaluator/evaluator.py `
  benchmarks/blindassist_last10m_perception_1/initial_program.py test
```

Do not launch a search on the mechanics fixtures. After real episodes are
frozen, run the same evaluator with `skydiscover-run` and the included config.

## Current bridge status

`evidence/ifc_reverse_side_prefix.json` is the first real non-OCR bridge input.
The raw two-view belief would have committed a large foreground/escalator
proposal even though portal-set truth was retained in `0/2` frames. Requiring a
center-and-approach observation to preserve or increase normalized target scale
changed that sequence from `SET_VALUED -> COMMIT` to
`SET_VALUED -> SET_VALUED`, eliminating this observed false commit. It did not
recover the correct door bank, so policy search remains blocked by the proposal
representation rather than evaluator or controller mechanics.
