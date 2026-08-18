# L10M-ORACLE-2

L10M-ORACLE-2 is the evaluator-hardened revision of the first runnable benchmark for a **monocular-RGB
deployment target, goal-driven last-ten-metre visual copilot**.  This first
stage deliberately isolates control from perception: the evaluator supplies
oracle target and safety observations and asks whether a searchable
`Last10mPolicy` can close the loop safely and reliably.

The complete `benchmarks/blindassist_last10m/` L10M-ORACLE-1 benchmark remains
immutable. Its first search is retained as an evaluator-shortcut case: the
score gain was entirely attributable to STOP being omitted from instruction
burden. L10M-ORACLE-2 is a new objective and its absolute scores must not be
compared with L10M-ORACLE-1 scores.

It does **not** train or validate YOLO, a VLM, optical flow, monocular depth, or
an end-to-end assistive product.  Synthetic viewpoint-graph success is not
evidence of real-user safety or BlindAssist product value.

## Search surface and protocol

Only the EVOLVE-BLOCK in `initial_program.py` may change:

```python
def decide(observation, memory):
    return action, confidence, new_memory
```

The evaluator owns action validation, observations, graph transitions, memory
bounds, episode timeouts, hard safety gates, aggregation, and artifacts.  A
candidate memory must be a JSON-serializable dictionary with at most 32
top-level keys and 4096 encoded bytes.  The baseline uses the conceptual FSM:

`IDLE -> SEARCH -> VERIFY -> LOCKED -> APPROACH -> REACQUIRE/STOPPED -> ARRIVED`

### Observation

| Field | Meaning |
| --- | --- |
| `target_visible` | Correctly perceived target visibility at this viewpoint |
| `target_bearing` | Signed target bearing in degrees; negative is left |
| `target_distance_class` | `far`, `medium`, or `near` |
| `target_confidence` | Oracle observation confidence exposed through the future perception interface |
| `target_identity_confidence` | Confidence that the visible candidate matches the requested target |
| `track_age`, `lost_steps` | Consecutive visible/lost frame counts computed by the runner |
| `corridor_left/center/right` | Currently traversable motion sectors |
| `closing_risk` | Normalized immediate closing/collision risk |
| `safety_confidence` | Confidence in the current safety observation |
| `heading_error` | Signed goal-facing error in degrees |
| `progress` | Bounded progress signal for the current route, not a future state/action |

The observation never contains node IDs, outgoing edges, a shortest path, the
correct next action, or future state.  The field set is deliberately compatible
with future arms that replace either target or safety oracle values with real
perception estimates.

### Actions

`SCAN_LEFT`, `SCAN_RIGHT`, `FORWARD`, `VEER_LEFT`, `VEER_RIGHT`, `SLOW_DOWN`,
`STOP`, and `ARRIVED` are the only legal actions.  `STOP` is a hold instruction,
not automatic episode success: temporal hazards can clear and a policy can then
reacquire.  Only a valid `ARRIVED` pose at the requested target succeeds.

## Interactive viewpoint graph

Each deterministic scenario is a directed graph.  A node contains the user's
viewpoint/orientation (implicit in its observation), an optional future RGB
reference slot, target and safety truth, traversable sectors, hazards, progress,
and outgoing action transitions.  An action selects the next node; an absent
edge holds the current viewpoint.  Thus candidate actions causally affect later
observations and may lengthen a route, lose the target, enter a hazard, approach
a decoy, oscillate, or time out.  Fixed video is intentionally not used as a
closed-loop evaluator.

`evaluator/scenarios/dev.json` is the cheap search-time set.  The evaluator
loader does not inject JSON files into SkyDiscover's candidate prompt.
`evaluator/scenarios/hidden.json` is a newly generated hidden-v2 and is used
only by `mode=test`. `evaluator/scenarios/regression_v1.json` is the consumed
L10M-ORACLE-1 hidden split, retained under `mode=regression` and no longer
described as held out. Repository-local
hidden data is an evaluation split, not a cryptographic secrecy boundary; a
formal external release should seal or remotely host it.

Development coverage:

1. straight entrance;
2. left entrance;
3. right entrance;
4. two similar targets;
5. glass/entrance decoy;
6. brief occlusion;
7. obstacle detour;
8. safety-confidence dip.

Hidden-v2 coverage:

1. offset target loss requiring directional reacquisition;
2. a transient crossing hazard;
3. a decoy followed by the requested target;
4. asymmetric final alignment.

The exact scenario hashes are frozen in `evaluator/scenarios/manifest.json`.

## Scoring and hard validity gate

Reported metrics are averages over the selected split except `validity`, which
is the minimum episode validity, and `reacquisition_success`, which is the rate
over episodes that actually contain a target-loss event.  Utility before the gate is:

```text
0.32 task_success
+ 0.20 safe_termination
+ 0.16 arrival_quality
+ 0.16 path_efficiency
+ 0.10 reacquisition_success
+ 0.04 wrong-way complement
+ 0.02 instruction-flip complement
- 0.015 instruction_count (capped at 10)
- 0.02 target_switch_count (capped at 3)
```

`instruction_count` counts actual action events emitted by `decide`; STOP,
SLOW_DOWN, scan, motion, and ARRIVED events all carry the same per-event
burden. The evaluator does not special-case action labels for this proxy.

If any episode is invalid, `combined_score = 0`, irrespective of utility.  An
illegal action, malformed return/memory, candidate crash, timeout, two
consecutive blind `FORWARD` actions, active motion with safety confidence below
0.60 or closing risk at least 0.75, wrong-target arrival, or premature/misaligned
arrival invalidates an episode.  Consequently a do-nothing policy cannot earn a
high score merely by avoiding motion.

Metrics include `combined_score`, `validity`, `task_success`,
`safe_termination`, `path_efficiency`, `wrong_way_steps`,
`reacquisition_success`, `target_switch_count`, `instruction_flip_rate`,
`instruction_count`, `arrival_quality`, `timeout_rate`, `mean_heading_error`,
`final_heading_error`, `unsafe_forward_count`, and
`premature_arrival_count`.

Failure artifacts describe observed failure events and aggregate episode
outcomes for the next Context Builder turn.  They never emit an oracle optimal
action sequence or graph adjacency.

Every evaluation also replays the evaluator-owned frozen v2 baseline on the
same split and emits a `score_attribution` receipt. It reports both the sum of
pre-gate component deltas and the final post-gate score delta; components
include success, safety, arrival, path, reacquisition, wrong-way, oscillation,
instruction, and target-switch terms. `SEARCH_SIGNAL_DETECTED`
means only that valid candidate score exceeds the same-revision baseline.
`HELDOUT_IMPROVEMENT_DETECTED` means only that this occurred in `mode=test`.

`BEHAVIORAL_IMPROVEMENT_DETECTED` is separate. It requires validity and no
regression in task success, safe termination, unsafe movement, or premature
arrival, plus a predeclared improvement in at least one of arrival quality,
path efficiency, reacquisition, wrong-way movement, instruction oscillation,
mean heading error, or final heading error. Instruction count alone cannot
pass this gate.

## Running

Direct deterministic evaluator replay (no Docker or model call):

```powershell
python benchmarks/blindassist_last10m_v2/evaluator/evaluator.py `
  benchmarks/blindassist_last10m_v2/initial_program.py train
python benchmarks/blindassist_last10m_v2/evaluator/evaluator.py `
  benchmarks/blindassist_last10m_v2/initial_program.py test
python benchmarks/blindassist_last10m_v2/evaluator/evaluator.py `
  benchmarks/blindassist_last10m_v2/initial_program.py regression
```

Bounded Codex CLI + Best-of-N smoke (this performs model calls; run only when
explicitly intended):

```powershell
codex login status
skydiscover-run benchmarks/blindassist_last10m_v2/initial_program.py `
  benchmarks/blindassist_last10m_v2/evaluator `
  -c benchmarks/blindassist_last10m_v2/config.yaml `
  --model codex-cli/gpt-5.6-sol --search best_of_n --iterations 10
```

The checked-in configuration fixes `best_of_n=3`, `num_context_programs=2`,
`max_parallel_iterations=1`, and full-rewrite generation.  SkyDiscover evaluates
development scenarios during search and automatically performs the authoritative
hidden `test` evaluation for the final best program.

## Experimental roadmap and claim boundary

The later controlled experiment is:

- Arm 0: frozen human baseline.
- Arm 1: Naked Codex with the same generation budget.
- Arm 2: SkyDiscover Best-of-N.
- Arm 3: SkyDiscover AdaEvolve.

Keep compatibility with `--search adaevolve` and `--search evox`, but authorize
EvoX only after evaluator stability, reproducible hidden replay, a Best-of-N
signal, and a search plateau have been demonstrated.

L10M-ORACLE-2 answers only: **under oracle perception, can search improve a
goal-driven last-ten-metre closed-loop control policy?**  It cannot establish
real monocular target detection, real hazard perception, monocular scale,
safe use by blind or low-vision people, or the value of the complete BlindAssist
system.  Future Arm B/C/D evaluations should independently replace goal and
safety oracles without changing this control contract.

Do not run Naked Codex, EvoX, or other comparative arms until a fixed-budget
SkyDiscover replay produces a clean hidden-v2 score gain and independently
passes the behavioral improvement gate. A reused/regression result, a score
gain attributable only to instruction burden, or one hidden split does not
establish general navigation superiority.

## Consumed outcome

The 2026-08-19 acceptance preflight exposed a second evaluator weakness before
the configured budget completed. The best program improved dev by `0.013125`
and hidden-v2 by `0.015`; score attribution assigned 100% of both deltas to
instruction burden. The v2 behavioral gate nevertheless reported PASS because
mean heading error improved even though heading did not contribute to score.

This is retained under `receipts/2026-08-19_acceptance_preflight/` as a
successful pipeline/evaluator-red-team result, not a navigation discovery.
Hidden-v2 is consumed and must not be reused as held out. L10M-ORACLE-3 fixes
the attribution-to-gate contract and introduces a new hidden-v3.
