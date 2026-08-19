# L10M-SKY-1 preregistration

L10M-SKY-1 is the direct SkyDiscover search-value trial after the consumed
L10M-COMP-1 and L10M-COMP-2 experiments. It asks one primary question: under
the same model, task prompt, initial policy, development evaluator, hidden
adjudicator, and resource ceilings, does the frozen Sky search treatment
produce a meaningfully better hidden BlindAssist policy than a direct
incumbent-only model loop?

## Arms and treatment contrast

- `naked_codex` is the direct control. Each call sees the task, current
  incumbent, and its development feedback. It has no multi-candidate archive
  context and always routes from the current incumbent.
- `sky_search` is the repository's already-developed COMP-1 Sky treatment:
  `best_of_n=3`, up to two ranked program contexts, and evaluator context
  injection. It reuses one sampled parent for three candidate additions before
  resampling the current best.

The common `Runner`, budget ledger, evaluator, hidden adjudicator, and receipt
machinery are a neutral outer platform. This experiment estimates the direct
increment from the declared Sky information and parent-routing treatment. It
does not estimate AdaEvolve, EvoX, GEPA, Synthesize, or every feature shipped in
the SkyDiscover repository.

## Fresh experimental units

The experimental unit is an independently generated L10M graph instance. The
design freezes 12 instances and two nested model replicates per instance.
Replicate effects are averaged within each instance; inference uses only the 12
instance effects. The 24 model runs per arm are never treated as independent
observations.

The deterministic cohort generator uses a new seed not used by COMP-2. Before
any treatment execution, it filters only on the frozen initial policy's
validity, success, safe termination, and preregistered score ceiling. Treatment
output cannot admit, reject, replace, or regenerate an instance.

## Fair budget and blind boundary

Every arm-instance-replicate receives at most 10 generation calls, 10
development evaluator attempts, and 300,000 input-plus-output tokens. All
failed or retried calls count. Hidden adjudication evaluates ten generation
opportunities in generation order only after both arms in a paired block have
terminated. Hidden outcomes are never returned to search.

The Codex provider runs in an ephemeral read-only working directory and gets
candidate context only through its prompt. This is application-level outcome
blindness, not hostile same-user OS isolation.

## Endpoint and frozen decision rule

For arm `a`, instance `i`, and replicate `s`, `S[a,i,s]` is the best hidden
substantive-score delta across ten adjudication opportunities. Invalid,
missing, failed, timed-out, or dev-inadmissible opportunities are zero. The
instance effect is:

`d_i = mean_s(S[sky_search,i,s] - S[naked_codex,i,s])`.

The primary location statistic is the mean of the 12 instance effects. Sky
direct value is established only when the observed mean exceeds `0.005` and an
exact one-sided instance-level sign-flip test against that margin has
`p <= 0.05`. Equivalence within `[-0.005, +0.005]` requires both frozen
one-sided tests; meaningful harm requires a mean below `-0.005` and its own
one-sided test. Failure of superiority alone is not equivalence.

Secondary behavioral discovery rate, anytime AUC, validity, safety, token use,
wall time, and cost-effectiveness curves cannot override the primary decision.
Any conclusion is bounded to this frozen parameterized L10M-ORACLE-3 graph
family and does not establish general navigation, product, or algorithm
superiority.

## Evidence states

The design protocol is committed before cohort generation. Cohort files and
every executable/configuration dependency must then be hash-bound by an
execution manifest before any treatment call is authorized. Search receipts,
hidden receipts, the frozen primary analysis, and descriptive closeout are
create-once artifacts.

## Frozen outcome

The completed trial contains 12 fresh instances, two nested seeds, 48 completed
arm runs, and 24 hidden paired adjudications. No arm-level failure occurred and
no hidden result was returned to search. Every arm remained within the frozen
ceilings; the observed maxima were 10 generation calls, 10 development
evaluations, and 259,323 input-plus-output tokens.

The frozen instance-level result is `DELTA_SKY = +0.00125`, below the
preregistered `+0.005` minimum meaningful effect. The one-sided exact test has
`p = 1.0`, with 3 wins, 6 ties, and 3 losses. Superiority was not established.
The separate frozen tests also established neither equivalence nor meaningful
harm. The architecture decision is therefore
`SKY_DIRECT_SEARCH_VALUE_NOT_ESTABLISHED`.

This result closes the planned route before Sky mechanism ablations. It does
not establish that SkyDiscover is generally ineffective; it says that this
frozen `best_of_n=3` Sky treatment did not establish direct incremental search
value over the Naked loop on this fresh L10M graph family. Under the planned
decision policy, the next work should diagnose the benchmark objective and
search space, rather than add EvoX, Ada, Shinka, or more search-framework
mechanisms.

The first descriptive secondary closeout omitted the preregistered ITT zero
floor when summarizing two all-negative Naked blocks. The original create-once
secondary receipt remains immutable. `SECONDARY_RESULTS_CORRECTION.json`
records the corrected Naked mean best substantive delta (`0.006666666667`) and
explicitly has no primary-gate authority. The frozen primary analysis already
applied the zero floor and is unaffected.
