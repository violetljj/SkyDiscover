# L10M-STRUCT-COMPONENT-2 preregistration

This is a create-once rerun of the unchanged COMPONENT-1 2x2 causal question.
It reuses the consumed 12-instance development cohort, but uses new seeds,
execution units, manifests, locks, receipts, and output roots. No COMPONENT-1
candidate, score, or receipt is an input to the formal estimand.

The first engineering attempt at this protocol reached eight terminal
generation units before a validation-import integrity defect was detected. It
is sealed as `ENGINEERING_ABORT_NO_ESTIMAND`; those units are not retried or
included. This frozen attempt uses a new manifest, run root, and seeds.

| Arm | Progress memory | Move proposals |
| --- | --- | --- |
| `raw_control` | OFF | OFF |
| `progress_only` | ON | OFF |
| `moves_only` | OFF | ON |
| `progress_moves` | ON | ON |

The scaffold, prompt text, config, candidate guard, evaluator, contracts,
budgets, selection rule, factorial questions, safety gate, and fresh-admission
gate are byte-identical to COMPONENT-1 and are referenced directly from its
frozen files. Only the formal random implementation and experiment engineering
are new.

## Complete blocks and failures

An `instance x seed` block is eligible only when all four arms have create-once
terminal search receipts. Infrastructure or orchestration terminal absence
excludes the entire block; partial arms are never retained. The experiment is
evaluable only with at least 70 of 72 complete blocks and at least five of six
complete seeds for every instance.

Arm-dependent failures are not missing data. Candidate invalidity, guard
rejection, unsafe output, arm-related evaluator failure, and any other terminal
arm failure remain in the complete block with the assigned arm scored zero.
A systemic evaluator-integrity failure makes the experiment `NOT_EVALUABLE`.

Within each instance, every arm selects its best robust-safe value from the
same complete seeds (six normally, five under the allowed missing-block rule).
The original progress main effect, moves main effect, interaction, safety gate,
and fresh-admission contrasts are then computed at the instance level.

## Isolation and recovery

Formal work runs in one Git-locked, exclusive, detached worktree at one frozen
commit until closeout. The launcher and every block, arm, adjudication,
analysis, and closeout entry check detached HEAD, frozen commit and tree,
tracked-tree cleanliness, and the external execution lock. Drift fails closed.

Generation remains local. CPU-heavy dev and hidden evaluation runs through the
task-owned AutoDL persistent worker channel. The local controller journals each
dispatch and validates the remote response before creating the local terminal
receipt. The remote worker never runs Codex CLI, edits Git, controls the
experiment, or becomes evidence authority.

At most two blocks may be active concurrently, never two seeds from the same
instance; all four arms of an active block are dispatched together. A started
unit without a terminal receipt is `in_doubt`, consumes budget, and is never
rerun. Once any arm in a block is in doubt, undispatched arms in that block are
not launched. Recovery continues only never-started blocks and valid terminal
work. This bounds a single launcher interruption to two blocks, matching the
predeclared 70/72 completeness allowance without authorizing replacement.
Consumed validation is also create-once: a `validation_started.json` without a
terminal validation receipt is never retried and is a systemic integrity
failure, not an infrastructure-missing block.

The result can only be a consumed-development mechanism-screen signal within
this graph family. Fresh execution remains separately preregistered and gated.
