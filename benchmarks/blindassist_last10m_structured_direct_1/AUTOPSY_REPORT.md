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

The receipts support exactly three conclusions:

1. Structured Direct's package-level value remains unestablished: the effect is
   `+0.001667`, the win/tie/loss count is `2/9/1`, and robust-safe coverage is
   only `10/12`.
2. Structured mechanisms did enter the selected candidates: progress memory is
   present in `11/12` and move proposals in `10/12`. The null package result
   therefore cannot be explained as simple non-adoption of those mechanisms.
3. No component-level attribution is admissible. Safety, tracking, progress,
   moves, and termination were almost always changed together, so individual
   benefits, harms, and interactions are not identified.

This closes `L10M-STRUCT-AUTOPSY-1`; further post-hoc dissection of this sealed
cohort is not warranted. The next admissible mechanism screen is
`L10M-STRUCT-COMPONENT-1`, a preregistered 2x2 contrast on consumed/development
tasks only:

| Arm | Progress memory | Move proposals |
| --- | --- | --- |
| A Raw control | OFF | OFF |
| B Progress only | ON | OFF |
| C Moves only | OFF | ON |
| D Progress + Moves | ON | ON |

All other bytes and experimental conditions should be held fixed as far as the
four toggles permit, including safety, tracking, termination, generation
budget, model, candidate count, selection, and evaluator. No new broad
Structured package search is justified. Fresh tasks remain reserved until at
least one of B, C, or D shows a clear, stable, robust-safe gain on the consumed
screen.

Run from the repository root:

```text
uv run python benchmarks/blindassist_last10m_structured_direct_1/autopsy.py \
  --receipt-root benchmarks/blindassist_last10m_structured_direct_1/receipts/execution
```
