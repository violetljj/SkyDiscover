# L10M-STRUCT-SEARCH-1

This is the preregistered searchability test authorized after L10M-DIAG-2.
DIAG-2 established post-hoc robust reachability on consumed data; this successor
asks whether bounded automated search can discover a qualifying policy on a new
12-instance cohort when given only a structured temporal candidate language.

The search language exposes safety, tracking, move proposal, progress, and
termination contracts.  It does not seed failed-action memory, a progress-level
repair, the `instance_07_H_08` trace, or the DIAG-2 oracle implementation.
Generated candidates are statically rejected if they import modules, access
files/processes/network-capable names, use dunder traversal, or contain frozen
oracle markers.

The three equal-budget arms are Naked Structured, EvoX Structured, and
Sky+EvoX Structured.  The absolute gate requires a search arm to achieve mean
hidden substantive delta strictly above `+0.005` and robust-safe behavior on
all 12 fresh instances.  Only after that gate may paired instance-level tests
establish EvoX incremental value and then Sky incremental value.

The cohort generator writes development and hidden splits to an external,
create-once private root.  The repository stores only hashes and logical paths.
Search receives development paths through the harness; hidden evaluation occurs
once after a complete paired block and is never returned to search.

This benchmark cannot establish real-world BlindAssist safety, deployment
readiness, general navigation performance, or unconstrained machine discovery.

`mechanical_preflight.json` is the preserved pre-format check. Formatting
changed executable source hashes, so the execution manifest binds the repeated
post-format `mechanical_preflight_v2.json`; the first receipt has no execution
authority.

## Frozen outcome

All 36 arm units and 12 paired hidden adjudications completed with six calls per
arm, no arm failures, no `in_doubt` calls, and no hidden feedback returned to
search. The frozen primary analysis did not establish searchability:

- EvoX Structured: mean substantive delta `+0.0041667`, below the strict
  `> +0.005` gate;
- Sky+EvoX Structured: mean `+0.0050000`, equal to rather than greater than the
  gate, and only 10/12 instances had a robust-safe candidate at the best primary
  value;
- EvoX minus Naked: `-0.0058333`, exact one-sided `p=1.0` under the frozen test.

The architecture decision is
`STRUCTURED_TEMPORAL_SEARCHABILITY_NOT_ESTABLISHED`. The original primary JSON
reported robust-safe counts of Naked 9, EvoX 8, and Sky+EvoX 9 because its
generation-order tie-break selected unsafe zero-value candidates over equally
scored safe candidates. The post-treatment audit found the intended counts were
12, 12, and 10. This defect does not change the decision because EvoX still
misses the mean gate and Sky+EvoX still misses both its strict mean and 12/12
safety requirements. The frozen primary result remains unmodified; the audit
has no override authority and no unit was rerun.
