"""Structured temporal candidate language without the DIAG-2 oracle solution.

Every named contract is independently editable.  The initial progress contract
is deliberately memory-free: it selects the first proposal and therefore does
not encode failed-action exclusion, progress-level memory, or the DIAG-2 repair.
"""

# EVOLVE-BLOCK-START
MOTION_ACTIONS = ("FORWARD", "VEER_LEFT", "VEER_RIGHT")


def safety_contract(observation, memory):
    """Return a mandatory safe action or ``None`` when motion may be considered."""
    if observation["safety_confidence"] < 0.60 or observation["closing_risk"] >= 0.75:
        memory["state"] = "STOPPED"
        return "STOP", 0.99
    return None


def tracking_contract(observation, memory):
    """Verify the target and provide bounded, non-advancing reacquisition."""
    visible = bool(observation["target_visible"])
    reliable = (
        visible
        and observation["target_confidence"] >= 0.55
        and observation["target_identity_confidence"] >= 0.60
    )
    if not reliable:
        lost_steps = int(observation["lost_steps"])
        if memory.get("state") in {"LOCKED", "APPROACH", "REACQUIRE"} and lost_steps <= 1:
            memory["state"] = "REACQUIRE"
            return "STOP", 0.92
        direction = memory.get("scan_direction", "SCAN_LEFT")
        memory["scan_direction"] = "SCAN_RIGHT" if direction == "SCAN_LEFT" else "SCAN_LEFT"
        memory["state"] = "SEARCH"
        return direction, 0.75
    if observation["track_age"] < 2:
        memory["state"] = "VERIFY"
        return "SLOW_DOWN", 0.80
    return None


def propose_moves(observation, memory):
    """Produce observable movement choices without hidden topology assumptions."""
    bearing = float(observation["target_bearing"])
    candidates = []
    if bearing < -12.0 and observation["corridor_left"]:
        candidates.append("VEER_LEFT")
    if bearing > 12.0 and observation["corridor_right"]:
        candidates.append("VEER_RIGHT")
    if observation["corridor_center"]:
        candidates.append("FORWARD")
    if observation["corridor_left"]:
        candidates.append("VEER_LEFT")
    if observation["corridor_right"]:
        candidates.append("VEER_RIGHT")
    return list(dict.fromkeys(candidates))


def progress_contract(observation, memory, candidates):
    """Select a proposal; the frozen seed intentionally has no temporal progress logic."""
    return candidates[0] if candidates else None


def termination_contract(observation, memory):
    """Provide a mandatory non-motion fallback when no proposal is admitted."""
    memory["state"] = "STOPPED"
    return "STOP", 0.98


def decide(observation, memory):
    """Compose the five search primitives into the evaluator's three-value interface."""
    memory = dict(memory or {})
    safety = safety_contract(observation, memory)
    if safety is not None:
        return safety[0], safety[1], memory
    tracking = tracking_contract(observation, memory)
    if tracking is not None:
        return tracking[0], tracking[1], memory
    memory["state"] = "LOCKED"
    if observation["target_distance_class"] == "near":
        if (
            abs(float(observation["heading_error"])) <= 15.0
            and observation["target_identity_confidence"] >= 0.80
        ):
            memory["state"] = "ARRIVED"
            return "ARRIVED", 0.96, memory
        candidates = ["VEER_LEFT" if observation["target_bearing"] < 0.0 else "VEER_RIGHT"]
    else:
        candidates = propose_moves(observation, memory)
    action = progress_contract(observation, memory, candidates)
    if action is None:
        fallback = termination_contract(observation, memory)
        return fallback[0], fallback[1], memory
    memory["state"] = "APPROACH"
    return action, 0.90, memory


# EVOLVE-BLOCK-END
