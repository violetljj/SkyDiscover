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
