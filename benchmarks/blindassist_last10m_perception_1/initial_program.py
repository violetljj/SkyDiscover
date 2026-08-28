"""BlindAssist L10 perception-policy baseline.

The evaluator supplies only measured perception/belief state.  The candidate
chooses the next observation or handoff action; it never receives truth labels.
"""


# EVOLVE-BLOCK-START
def decide(observation, memory):
    memory = dict(memory or {})
    state = observation["perception_state"]
    candidates = observation["candidates"]
    lost_steps = int(observation["lost_steps"])
    safe = bool(observation["safe_to_approach"])

    if not safe:
        memory["mode"] = "HOLD"
        return "HOLD", 0.99, memory

    if state == "REACQUIRE" or lost_steps:
        memory["mode"] = "REACQUIRE"
        return "SCAN_LAST_BEARING", 0.94, memory

    if state == "SEARCH" or not candidates:
        memory["mode"] = "SEARCH"
        return "SWEEP", 0.85, memory

    if state == "SET_VALUED":
        memory["mode"] = "DISAMBIGUATE"
        return "CENTER_AND_APPROACH", 0.90, memory

    if state == "COMMIT":
        memory["mode"] = "TRACK"
        if observation["handoff_ready"]:
            return "ARRIVED", 0.97, memory
        return "TRACK", 0.95, memory

    memory["mode"] = "HOLD"
    return "HOLD", 0.70, memory
# EVOLVE-BLOCK-END
