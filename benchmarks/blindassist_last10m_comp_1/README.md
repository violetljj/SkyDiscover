# L10M-COMP-1 preregistration

L10M-COMP-1 is the next causal experiment after the consumed L10M-ORACLE-3
acceptance run. It asks whether SkyDiscover's search structure adds discovery
value beyond the same `gpt-5.6-sol` model used through a minimal incumbent-only
control, and whether EvoX improves discovery rate, quality, or efficiency.

The mechanical design was frozen before hidden-v4 was materialized. The common
budget-accounting harness subsequently passed synthetic preflight, and fresh
hidden-v4 was generated from seed `40419`, checked only against the frozen
baseline, and sealed in `execution_manifest.json`. Arm execution is now
authorized only through the manifest-verifying harness.

## Arms

- `skydiscover`: Best-of-N with `best_of_n=3`.
- `naked_codex`: an incumbent-only loop. Each generation sees the common task
  context, the initial program, and the current incumbent plus its dev feedback;
  it receives no archive, lineage, multiple-candidate context, or search-strategy
  generation.
- `evox`: the repository EvoX controller. Every solution-generation and
  search-strategy-generation model call counts against the same ceilings.

Every arm starts from byte-identical L10M-ORACLE-3 initial code, uses the same
model and reasoning effort, and has access to the same frozen evaluator
semantics and dev information channel. Algorithm-specific organization of that
information is the treatment, not an unfair information grant.

## Budget and retry contract

Each arm in each paired replicate is stopped by the first exhausted ceiling:

- 10 total model generation calls;
- 10 dev evaluator attempts;
- 300,000 total model tokens (`input_tokens + output_tokens`);
- no more than one provider retry for a failed generation.

All calls count, including failed, malformed, compile-failing, retry, and EvoX
meta-search calls. A provider retry consumes another generation call and its
tokens. A compile or evaluator retry consumes another evaluator attempt. The
harness, not an arm, applies these rules. Wall time is recorded but is not a
fairness budget.

The 300,000-token ceiling is fixed just above the observed 291,255-token total
from the completed ten-call ORACLE-3 run. The aggregate and per-call usage are
preserved in `budget_basis.json`; reasoning tokens are a subset of output tokens
and are not double-counted. The ceiling is not tuned per arm.

## Replicates and isolation

Run three paired replicate blocks with local seeds `101`, `202`, and `303`.
The seeds control harness ordering and supported local randomness; they do not
claim to seed provider-side model sampling. Arm order is rotated by block.
Each arm has isolated output, cache, checkpoint, and process roots. Candidates
or feedback never cross arms or replicates.

## Evaluation boundary

Search receives dev feedback only. After all arms in a block terminate, a
blind adjudicator evaluates every dev-admitted candidate exactly once on fresh
hidden-v4, in generation order. Malformed, failed, or otherwise dev-inadmissible
generation opportunities are padded with zero rather than recovered or retried
during adjudication. Hidden results are never returned to any arm.
The ten hidden adjudication attempts per arm are a separate, equal post-search
budget and are not counted as search evaluator calls.

Hidden-v3 and all earlier hidden splits are consumed regression evidence only.
No threshold, arm, retry rule, ordering rule, or endpoint may change after
hidden-v4 is materialized.

## Endpoints

The primary endpoint is replicate-level hidden substantive behavioral discovery:
whether any candidate passes the unchanged ORACLE-3 behavioral gate, including
validity, task success, safety, scored behavioral contribution, and the frozen
50% attribution threshold.

Secondary endpoints are final best hidden substantive delta, final raw hidden
score, model tokens, generation and evaluator calls, success rate, paired arm
wins, and tokens-to-first-threshold.

Behavioral anytime AUC is computed over hidden adjudications as the normalized
area under the best-so-far substantive-score-delta curve. Invalid or missing
candidates contribute zero, the x-axis is evaluator attempt 1 through 10, and
the curve is divided by 10 but not normalized by the best arm. This preserves
absolute effect size while measuring how early it was discovered.

The main comparisons are SkyDiscover versus Naked Codex and EvoX versus
SkyDiscover. With only three replicates, results are bounded within
L10M-COMP-1 and reported descriptively; they do not establish general model or
algorithm superiority.

## Claim rules

`SEARCH_SYSTEM_INCREMENTAL_VALUE_ESTABLISHED_WITHIN_L10M_COMP_1` requires
SkyDiscover to beat Naked Codex in all three paired replicates on the primary
binary endpoint, with no safety regression. Any tie or discordant replicate
retains the weaker `COMPARATIVE_SIGNAL_DETECTED_WITHIN_L10M_COMP_1` ceiling.

`EVOX_INCREMENTAL_VALUE_ESTABLISHED_WITHIN_L10M_COMP_1` uses the same rule for
EvoX versus SkyDiscover. Secondary metrics explain quality and efficiency but
cannot override a failed primary rule.
