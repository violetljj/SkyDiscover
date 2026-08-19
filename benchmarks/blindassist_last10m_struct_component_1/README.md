# L10M-STRUCT-COMPONENT-1 preregistration

`L10M-STRUCT-COMPONENT-1` is a consumed/development mechanism screen. It is the
next evidence node after `L10M-STRUCT-AUTOPSY-1`, which established that
Structured Direct did not demonstrate package value, that progress memory and
move proposals were actually adopted, and that their individual contributions
were not identifiable because the generated candidates changed the full
contract package.

This experiment does not revisit that sealed autopsy and has no fresh or blind
claim authority. It reuses the already consumed 12-instance `L10M-COMP-2`
cohort. Generation sees each consumed `dev` split; the old `hidden` split is a
consumed validation split used only after all four arms in a paired block are
terminal. Its results never return to generation.

## Frozen 2x2 design

| Arm | Progress memory | Move proposals |
| --- | --- | --- |
| `raw_control` | OFF | OFF |
| `progress_only` | ON | OFF |
| `moves_only` | OFF | ON |
| `progress_moves` | ON | ON |

All arms start from the same byte-identical scaffold and common config. The
only prompt difference is the assigned component capability. The candidate
guard runs before evaluator import and compares source bytes after masking only
the function bodies admitted for that arm. Every generated candidate also
changes one exact, semantically inert `CANDIDATE-TAG` comment from `initial` to
`generated`; this common mechanical difference prevents an unchanged control
candidate from being deduplicated against the iteration-zero program:

- `raw_control`: no mutable function;
- `progress_only`: `progress_contract` only;
- `moves_only`: `propose_moves` only;
- `progress_moves`: those two functions only.

`safety_contract`, `tracking_contract`, `termination_contract`, `decide`, every
other executable module byte, the model, reasoning effort, one-call generation budget,
six-candidate opportunity count, selection rule, evaluator, and failure
semantics are common. Progress code cannot contain action literals and may use
only registered progress-memory keys. Move proposals receive no memory and
must use current observable corridor geometry. Any boundary violation rejects
the whole candidate and contributes the preregistered ITT zero.

## Estimands

For each instance, each arm first selects its best robust-safe consumed-
validation value across six fresh-start candidates. Let the selected arm values
be `A`, `B`, `C`, and `D` in table order. The factorial estimands are:

\[
P = \operatorname{mean}_i\left(\frac{(B_i-A_i)+(D_i-C_i)}{2}\right)
\]

\[
M = \operatorname{mean}_i\left(\frac{(C_i-A_i)+(D_i-B_i)}{2}\right)
\]

\[
I = \operatorname{mean}_i(D_i-B_i-C_i+A_i)
\]

These estimate the progress-memory main effect, move-proposal main effect, and
their interaction under this frozen generation language. Simple `B-A`, `C-A`,
and `D-A` contrasts govern fresh admission. No result can retrospectively
attribute the old Structured Direct package effect.

## Safety and fresh admission

Invalid, missing, failed, timed-out, or non-robust-safe candidates score zero.
A treatment arm passes the safety gate only when its selected candidate is
valid, task-successful, and safely terminating on all 12 consumed instances.

At least one of `B-A`, `C-A`, or `D-A` must independently meet every condition
below before a separate fresh preregistration is admissible:

1. mean effect strictly greater than `0.005`;
2. one-sided instance-level exact sign-flip `p <= 0.05/3`;
3. treatment robust-safe on `12/12` instances;
4. every leave-one-instance-out mean remains strictly positive.

Passing only authorizes drafting and reviewing a new fresh protocol. It does
not authorize automatic fresh execution or a component superiority claim.

## Recovery boundary

There are 288 assigned generation units: 12 instances by 6 replicates by 4
arms. Each unit has one external generation call. `unit_started.json` is
written create-once before dispatch; absence of a terminal receipt after that
record makes the unit `in_doubt`, consumes its budget, and forbids rerun. A
terminal receipt may be skipped on task-level resume only after validation.
Iteration-level resume is not applicable. The maximum lost work is one call.
`progress.py` is a read-only summarizer and never changes processes, receipts,
locks, candidates, or evaluator state.

No arm may run until `receipts/mechanical_preflight.json`, the final frozen
protocol status, and `execution_manifest.json` all agree and the harness
verifies every bound hash.
