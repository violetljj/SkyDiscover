# `codex/goal-copilot-2b-protocol`

- Purpose: record SkyDiscover's fail-closed proposal/search-side contract for
  the BlindAssist-owned GOAL-COPILOT-2B protocol design.
- Base branch: `origin/codex/goal-copilot-1-sky-pilot`.
- Base commit: `d0647244880dfdced5abad36c4b3dd9f7171f7ae`.
- Task-owned scope: `benchmarks/blindassist_goal_copilot_2b/`, its focused test,
  and this branch record.
- Dependencies: BlindAssist GC2-A terminal closeout and the matching tracked
  BlindAssist GC2-B protocol SHA-256.
- Work performed: froze the authority split, proposed two-by-16 search budget,
  immutable starting-policy identity, non-executable search blueprint, and
  fail-closed execution prerequisites.
- Current status: protocol design implemented; search and model calls remain
  unauthorized; provider, SearchTaskBundle, held-out envelope, and formal run
  seal are intentionally absent.
- Evidence-backed result: contract validation can establish internal design
  consistency and non-executability only.
- Claim ceiling:
  `symbolic_consumed_task_noise_robust_search_protocol_design_only`.
- Validation: focused contract test and scoped diff check required before push.
- Important commits: `4f5c2ecccba27bba953c9a750b0434cd7f43de66`
  adds and validates the non-executable Sky contract.
- Integration target: retain on the task branch until a separately authorized
  formal GC2-B implementation selects its frozen base.
- Readiness/blockers: design is ready; execution is blocked on all prerequisites
  named above and separate authorization.
- Final disposition: protocol-design contract complete and ready for push to
  `origin/codex/goal-copilot-2b-protocol`; no execution resources were started.
