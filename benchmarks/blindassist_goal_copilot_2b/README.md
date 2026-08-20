# BlindAssist GOAL-COPILOT-2B Sky contract

This directory records SkyDiscover's proposal-side agreement with the frozen
BlindAssist GC2-B protocol design. It is deliberately non-executable:
`search_blueprint.json` is disabled, has no frozen model provider, and cannot be
used as a Sky configuration.

BlindAssist retains task semantics, corruption schedules, hidden state,
evaluator, safety, winner lock, held-out material, and acceptance authority.
SkyDiscover may receive a public development SearchTaskBundle and propose
candidates only after a separate formal run seal explicitly authorizes calls.

The maximum later budget is two replicates of 16 generation attempts. The
contract does not materialize that budget, perform provider preflight, export
held-out schedules, invoke a model, or start a search.

Claim ceiling:
`symbolic_consumed_task_noise_robust_search_protocol_design_only`.
