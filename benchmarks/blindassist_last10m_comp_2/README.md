# L10M-COMP-2 preregistration

L10M-COMP-2 is a fresh, instance-level adjudication of two fixed estimands:

\[
\Delta_E = \operatorname{EvoX} - \operatorname{Naked\ Codex}
\]

\[
\Delta_H = \operatorname{Sky{+}EvoX} - \operatorname{EvoX}
\]

COMP-1 is consumed development evidence. It may be used for implementation
debugging and variance calibration, but no COMP-1 outcome can enter a COMP-2
claim.

## Experimental unit and cohort

The experimental unit is one independently generated L10M graph instance.
The frozen cohort contains 12 instances and two nested search replicates per
instance. Replicates reduce within-instance search noise; the primary analysis
first averages paired replicate effects within each instance and then performs
inference over the 12 instance effects. It never treats the 24 runs as
independent observations.

The cohort generator uses only a fixed random seed, graph-family constraints,
and the frozen initial policy. Before any treatment runs, an instance is
admitted only when both its development and hidden baseline scores are below
the preregistered ceiling. No treatment output may be used to retain, replace,
or regenerate an instance.

## Common outer harness and arms

All arms use the same SkyDiscover `Runner`, budget ledger, evaluator, receipt
format, candidate ordering, and hidden adjudicator. Those mechanics are the
neutral outer experimental platform, not part of either treatment.

- `naked_codex`: incumbent-only generation with no archive, lineage, or
  multi-candidate context.
- `evox`: the repository EvoX controller with its frozen standard initial
  search strategy.
- `sky_evox`: the same EvoX controller initialized with the frozen
  `SkyBestOfThreeInitialDatabase`. This is the only Sky search-layer
  intervention: for the initial strategy window it reuses the current best
  parent for three candidate additions and supplies top-program context. EvoX
  may subsequently evolve that strategy under exactly the same switching,
  migration, scoring, and termination rules as standalone EvoX.

Thus `Delta_H` is specifically the incremental effect of **Sky best-of-three
initial candidate routing inside EvoX**. It is not an estimate of generic Sky
infrastructure value or of every possible Sky search composition.

Except for the declared initial database file, the two EvoX arms have
byte-identical configuration, prompt, model, reasoning effort, variation
operators, search-strategy evaluator, call ceilings, evaluator-attempt ceiling,
token ceiling, and termination rules.

## Primary endpoint and gatekeeping

For arm `a`, instance `i`, and nested replicate `s`, let `S[a,i,s]` be the best
hidden substantive score delta across the ten preregistered adjudication
opportunities. Invalid, missing, failed, timed-out, or dev-inadmissible
opportunities score zero. The instance effects are arithmetic means across the
two paired replicates:

\[
d^E_i = \operatorname{mean}_s(S[EvoX,i,s]-S[Naked,i,s])
\]

\[
d^H_i = \operatorname{mean}_s(S[Sky{+}EvoX,i,s]-S[EvoX,i,s])
\]

Both minimum meaningful effects are frozen at `0.005` substantive-score units.
At one-sided `alpha=0.05`, G1 tests `Delta_E > 0.005` using an instance-level
exact sign-flip test. G2 tests `Delta_H > 0.005` only if G1 passes. The test's
symmetry/exchangeability assumption and all observed instance effects are
reported. Win/tie/loss is descriptive; the frozen tie interval is
`[-0.005, +0.005]`.

Failure of G2 superiority does not establish equivalence. Equivalence requires
both preregistered one-sided sign-flip tests against `-0.005` and `+0.005` to
pass. Meaningful harm is tested separately as `Delta_H < -0.005`.

## Secondary endpoints

Secondary results cannot open or override a primary gate. They include
behavioral anytime AUC, primary behavioral success, validity, safe termination,
win/tie/loss, generation calls, evaluator attempts, token use, wall time, and a
cost-effectiveness curve. Token ratios are not primary estimands.

## Evidence and execution boundary

`protocol.json` is frozen before cohort materialization. `cohort_manifest.json`
and `execution_manifest.json` must bind every generated instance, evaluator,
arm configuration, search strategy, and analysis file before treatment
execution is authorized. Search receives development feedback only. Hidden
results are evaluated only after every arm in a paired block terminates and are
never returned to search.

The Codex backend runs ephemerally in a separate read-only temporary directory
and receives candidate context only through its prompt. This is an
application-level blind boundary, not hostile same-user OS isolation.

## Frozen outcome

COMP-2 completed all 72 assigned arm runs and all 24 paired hidden
adjudications with zero arm-level failures. No search process received hidden
results. The maximum observed use in any arm was 10 generation calls, 10
development evaluator attempts, and 235,474 tokens, all within the frozen
ceilings.

G1 did **not** establish EvoX incremental value:

- observed instance-level mean `Delta_E = 0.0020833`;
- minimum meaningful effect `delta_E = 0.005`;
- exact one-sided sign-flip `p = 1.0` under the frozen rule;
- instance distribution: `2 wins / 9 ties / 1 loss` using the frozen tie band.

Because G1 failed, fixed-sequence gatekeeping did not open G2. Therefore the
experiment makes no formal superiority, equivalence, or harm decision for the
Sky best-of-three initialization. Its descriptive mean was
`Delta_H = -0.0041667` with `0 wins / 9 ties / 3 losses`, but that result has no
G2 claim authority.

Descriptive secondary endpoints were:

| Arm | Behavioral discoveries | Mean best substantive delta | Mean anytime AUC | Total tokens |
| --- | ---: | ---: | ---: | ---: |
| Naked Codex | 9/24 | 0.004583 | 0.002375 | 5,397,087 |
| EvoX | 11/24 | 0.006667 | 0.005333 | 5,505,782 |
| Sky + EvoX | 5/24 | 0.002500 | 0.001917 | 5,452,750 |

EvoX retains a descriptive positive lead over Naked Codex, including better
anytime behavior, but the gain is below the preregistered minimum meaningful
effect and does not establish incremental value. The architecture verdict is
`EVOX_INCREMENTAL_VALUE_NOT_ESTABLISHED_G2_NOT_TESTED`; this experiment does
not authorize replacing Sky-native search with EvoX or retaining the tested
Sky+EvoX composition as a proven gain layer.

The external-validity ceiling is the frozen parameterized
L10M-ORACLE-3 graph family. These independently seeded parameterizations do not
establish performance over unrelated navigation tasks or broader search
domains. Primary details are in `receipts/execution/FINAL_RESULT.json`;
descriptive endpoints and receipt hashes are in `SECONDARY_RESULTS.json` and
`EXECUTION_AUDIT.json`.
