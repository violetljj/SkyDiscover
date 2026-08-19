# L10M-STRUCT-AUTOPSY-1

This is a receipt-only, post-hoc mechanism autopsy of the sealed
`L10M-STRUCT-DIRECT-1` cohort. It performed **zero fresh tasks and zero model
calls**. Existing hidden adjudications and candidate manifests were read
without changing, re-evaluating, or retrying any unit.

## Findings

- The paired result is unchanged: Structured Direct minus Raw Direct is
  `+0.001667`, with `2` wins, `9` ties, and `1` loss under the frozen tie
  interval. Structured robust-safe coverage remains `10/12`.
- The selected Structured candidates changed all five named contract bodies in
  all 12 instances. Therefore this cohort cannot identify an individual
  contract's causal contribution.
- Conservative static feature tags show progress memory in `11/12` selected
  candidates, move proposals in `10/12`, and safety, tracking, and termination
  features in `12/12`. Their descriptive paired means are respectively
  `+0.001818`, `+0.002000`, and `+0.001667` for the latter three. These are
  associations among selected package outputs, not ablation estimates.
- The only positive paired blocks are `instance_06` (`+0.02`) and `instance_08`
  (`+0.01`); the only negative block is `instance_12` (`-0.01`). The remaining
  nine blocks are frozen ties. The two safety failures are `instance_01` and
  `instance_02`.

## Interpretation boundary

The receipts support a narrower conclusion: the package-level result is not
explained by a consistently separable single contract in this cohort. Because
the generated candidates are compositional and nearly all selected candidates
contain the same contract families, no component-level causal claim is
admissible. The next fresh experiment, if authorized, should therefore be a
pre-registered single-mechanism contrast (for example Raw Direct plus a
minimal progress contract), not another full-package comparison.

Run from the repository root:

```text
uv run python benchmarks/blindassist_last10m_structured_direct_1/autopsy.py \
  --receipt-root benchmarks/blindassist_last10m_structured_direct_1/receipts/execution
```
