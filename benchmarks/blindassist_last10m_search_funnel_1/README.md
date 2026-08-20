# L10M-SEARCH-FUNNEL-1

This is a zero-call, receipt-only diagnostic over the consumed `L10M-SKY-1`
cohort. It localizes the next search-mechanism question without reopening the
terminated Structured-component route.

The audit joins four already-sealed views for every arm/block:

1. generated candidate identity and order from `candidate_manifest.json`;
2. development metrics and parent/context lineage from checkpoint 10;
3. the runner's retained best program from `best_program_info.json`; and
4. the immutable per-candidate hidden adjudication receipt.

It measures whether robust-safe positive candidates existed, whether the
development-selected retained program preserved their hidden value, and how
often development-improving children converted into hidden improvements. The
hidden result is used only for post-hoc diagnosis and never returned to search.

The external run root is read-only input. The audit refuses incomplete or
identity-inconsistent evidence and never invokes a model or evaluator. A
preregistered missing candidate opportunity is accepted only when the archived
hidden row preserves it as an explicit ITT zero; it is never imputed.

```powershell
uv run python benchmarks/blindassist_last10m_search_funnel_1/audit.py `
  --run-root E:\SkyDiscover\.runs\l10m_sky_1_20260819 `
  --output benchmarks/blindassist_last10m_search_funnel_1/receipts/funnel_audit.json
```

The result can authorize a consumed-development mechanism experiment only. It
cannot establish search superiority, real-world safety, or a fresh/blind gain.

## Frozen outcome

The completed receipt is `receipts/funnel_audit.json`; the bounded human-readable
interpretation is in `RESULT.md`. The decision is `MIXED_OR_UNRESOLVED`.
Selection/retention loss did not pass its preregistered signal gate, and robust-safe
positive candidates were not scarce enough to pass the absolute scarcity gate.
The next development target is therefore incremental candidate quality relative
to the strong Naked baseline, not a Structured or selection rescue.
