# EVOLVE-BLOCK-START
def decide(observation, memory):
    """Fast-lock only on strong evidence; otherwise verify, stop, and reacquire safely."""
    memory = dict(memory or {})
    state = memory.get("state", "IDLE")
    scan = memory.get("scan_direction", "SCAN_LEFT")

    visible = bool(observation["target_visible"])
    confidence = float(observation["target_confidence"])
    identity = float(observation["target_identity_confidence"])
    bearing = float(observation["target_bearing"])
    distance = observation["target_distance_class"]
    track_age = int(observation["track_age"])
    lost_steps = int(observation["lost_steps"])

    # Unconditional safety gate.
    if (
        float(observation["safety_confidence"]) < 0.60
        or float(observation["closing_risk"]) >= 0.75
    ):
        memory["state"] = "STOPPED"
        return "STOP", 0.99, memory

    confirmed = visible and confidence >= 0.55 and identity >= 0.60
    if not confirmed:
        if state in {"LOCKED", "APPROACH", "REACQUIRE"} or lost_steps:
            memory["state"] = "REACQUIRE"
            if lost_steps <= 1:
                return "STOP", 0.92, memory

        memory["state"] = "SEARCH"
        memory["scan_direction"] = (
            "SCAN_RIGHT" if scan == "SCAN_LEFT" else "SCAN_LEFT"
        )
        return scan, 0.75, memory

    # Strong, mutually supporting evidence permits immediate lock. Ambiguous
    # targets still require a second observation, preserving decoy resistance.
    strong_lock = confidence >= 0.85 and identity >= 0.85
    if track_age < 2 and not strong_lock:
        memory["state"] = "VERIFY"
        return "SLOW_DOWN", 0.84, memory

    memory["state"] = "LOCKED"

    if distance == "near":
        if abs(float(observation["heading_error"])) <= 15.0 and identity >= 0.80:
            memory["state"] = "ARRIVED"
            return "ARRIVED", 0.97, memory

        memory["state"] = "APPROACH"
        return ("VEER_LEFT" if bearing < 0.0 else "VEER_RIGHT"), 0.88, memory

    memory["state"] = "APPROACH"
    if bearing < -8.0 and observation["corridor_left"]:
        return "VEER_LEFT", 0.90, memory
    if bearing > 8.0 and observation["corridor_right"]:
        return "VEER_RIGHT", 0.90, memory
    if observation["corridor_center"]:
        return "FORWARD", 0.90, memory
    if observation["corridor_left"]:
        return "VEER_LEFT", 0.82, memory
    if observation["corridor_right"]:
        return "VEER_RIGHT", 0.82, memory

    memory["state"] = "STOPPED"
    return "STOP", 0.98, memory
# EVOLVE-BLOCK-END