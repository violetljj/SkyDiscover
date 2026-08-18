# L10M-ORACLE-3

L10M-ORACLE-3 is the attribution-gated revision of the deterministic
BlindAssist last-ten-metre control benchmark. It preserves L10M-ORACLE-1 and
L10M-ORACLE-2 unchanged. Both earlier hidden splits are consumed and are
available only as `regression_v1` and `regression_v2`.

This remains an oracle-perception, synthetic viewpoint-graph benchmark. It
does not establish real monocular perception, real-user safety, or complete
BlindAssist product value.

## Revision contract

Only `decide(observation, memory)` inside the EVOLVE-BLOCK is searchable. The
evaluator owns observations, graph transitions, action validation, memory
bounds, aggregation, hard safety gates, and score attribution.

All returned actions are actual instruction events. STOP, SLOW_DOWN, scan,
movement, and ARRIVED therefore carry the same instruction-count burden. The
utility function is unchanged from L10M-ORACLE-2:

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

Invalid candidates receive `combined_score = 0`. Invalidity includes malformed
returns or memory, crashes, timeout, illegal actions, unsafe active motion,
continued blind forward motion, and wrong or premature ARRIVED actions.

## Attribution and substantive gate

Every candidate is compared with the evaluator-owned frozen baseline on the
same split. `score_attribution` reports component deltas and the final score
delta. `SEARCH_SIGNAL_DETECTED` and `HELDOUT_IMPROVEMENT_DETECTED` describe
score movement only; neither implies navigation improvement.

`BEHAVIORAL_IMPROVEMENT_DETECTED` requires all of the following:

1. validity, task success, and safe termination are preserved;
2. unsafe movement and premature arrival do not regress;
3. at least one scored behavioral metric improves by the predeclared minimum;
4. scored components other than instruction burden have positive net delta;
5. those substantive components explain at least 50% of total positive score delta.

The scored behavioral metrics are arrival quality, path efficiency,
reacquisition, wrong-way movement, instruction oscillation, and target switch.
Unscored diagnostics such as mean heading error cannot make this gate pass.

## Splits and evidence roles

- `dev.json`: ten search-time scenarios. D09 and D10 deliberately provide
  baseline path-efficiency headroom through moderate left/right alignment.
- `hidden.json`: four newly generated, pre-frozen hidden-v3 scenarios.
- `regression_v2.json`: consumed L10M-ORACLE-2 hidden-v2.
- `regression_v1.json`: consumed L10M-ORACLE-1 hidden.

Exact hashes and evidence roles are frozen in `evaluator/scenarios/manifest.json`.
The JSON scenario files are excluded from evaluator-context prompt injection.
Repository-local hidden data is an evaluation split, not a cryptographic
secrecy boundary; formal external evaluation should remotely seal it.

## Running

```powershell
python benchmarks/blindassist_last10m_v3/evaluator/evaluator.py `
  benchmarks/blindassist_last10m_v3/initial_program.py train

skydiscover-run benchmarks/blindassist_last10m_v3/initial_program.py `
  benchmarks/blindassist_last10m_v3/evaluator `
  -c benchmarks/blindassist_last10m_v3/config.yaml `
  --model codex-cli/gpt-5.6-sol --search best_of_n --iterations 10
```

The fixed search configuration uses the same model and Best-of-N budget as the
consumed v2 preflight. Do not run Naked Codex, EvoX, or other comparative arms
unless a clean hidden-v3 gain also passes the substantive gate. Absolute scores
must not be compared across evaluator revisions.

## Frozen acceptance outcome

The canonical adjudicated claim for this run is:

`SUBSTANTIVE_POLICY_IMPROVEMENT_ESTABLISHED_WITHIN_L10M_ORACLE_3`

The 2026-08-19 fixed-budget run completed all ten iterations. The final best
improved hidden-v3 from `0.879167` to `0.935000`. Path efficiency improved from
`0.791667` to `1.000000`; scored behavioral components contributed `0.033333`
of the `0.055833` score gain, a `59.7018%` substantive share. All validity and
safety metrics remained clean, so both heldout score and behavioral gates pass.

On dev, the same best improved path efficiency from `0.90` to `1.00`, but its
substantive share was `49.2308%`, below the frozen 50% threshold; the dev
behavioral gate therefore remains FAIL. No threshold was changed after seeing
the result. The full receipt and exact best program are stored under
`receipts/2026-08-19_acceptance/`. The original receipt remains unchanged; the
claim upgrade and its source hash are recorded separately in
`claim_adjudication.json`.

This establishes a meaningful navigation search result only inside the
L10M-ORACLE-3 oracle-graph contract. It is sufficient to justify a separately
frozen Naked Codex/EvoX comparison, but does not itself establish general
superiority or deployment safety.

Hidden-v3 is consumed. It must not be used again as heldout evidence or as a
target for further search. The next causal question is preregistered under
`benchmarks/blindassist_last10m_comp_1/`; no real BlindAssist navigation-policy
optimization is authorized by this result.
