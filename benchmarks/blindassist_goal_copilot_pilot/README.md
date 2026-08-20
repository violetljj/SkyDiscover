# BlindAssist Goal-Copilot Sky Pilot adapter

This adapter runs only SkyDiscover's canonical `best_of_n` proposal loop. The
BlindAssist SearchTaskBundle supplies the immutable development evaluator and
baseline. The adapter has no fresh cohort and no acceptance authority.

Each formal replicate is create-once, sequential, zero-retry, and limited to 16
generation dispatches. The durable JSONL journal records generation start before
the Codex CLI dispatch and accepted/failed completion afterwards. A started-only
record is `IN_DOUBT` and consumes its frozen opportunity.
