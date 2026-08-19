# Branch ledger

This directory is the durable index for project-owned work branches. It exists
to make later review, handoff, integration, and deletion decisions fast without
reconstructing branch intent from commit subjects alone.

Store one Markdown record per branch in `branches/`. Replace `/` in the branch
name with `__`; for example, `codex/example-task` becomes
`branches/codex__example-task.md`.

A record is created with the branch's first meaningful commit and updated only
when scope or status materially changes, or before handoff, integration,
abandonment, or deletion. It must contain:

- branch, status, owner, base branch and exact base commit;
- purpose, task-owned scope, exclusions, and dependencies;
- work performed and important commits;
- evidence-backed result, claim ceiling, and validation;
- integration target, readiness, blockers, integrated commit, or disposition.

Use `unknown`, `not run`, or `not integrated` when the repository does not prove
a historical fact. Do not turn a development result into a fresh/blind claim.
Review this record together with the branch diff before integration. Records are
retained after their branches are deleted.

## Status vocabulary

- `active`: work is in progress.
- `ready_for_review`: branch work is complete and awaits integration review.
- `blocked`: a named blocker prevents progress or integration.
- `integrated`: the recorded branch revision has entered its target branch.
- `closed_not_integrated`: work ended without integration; the reason is stated.
