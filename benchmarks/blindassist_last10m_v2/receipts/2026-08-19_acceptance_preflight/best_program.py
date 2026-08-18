"""Conservative closed-loop policy with confidence-based fast verification."""


# EVOLVE-BLOCK-START
def decide(observation, memory):
    """Track a safely verified target, skipping redundant verification only when
    independent target and identity confidence are both exceptionally strong.
    """
    memory = dict(memory or {})
    state = memory.get("state", "IDLE")
    scan_direction = memory.get("scan_direction", "SCAN_LEFT")

    visible = bool(observation["target_visible"])
    bearing = float(observation["target_bearing"])
    distance = observation["target_distance_class"]
    target_confidence = float(observation["target_confidence"])
    identity_confidence = float(observation["target_identity_confidence"])
    track_age = int(observation["track_age"])
    lost_steps = int(observation["lost_steps"])
    safety_confidence = float(observation["safety_confidence"])
    closing_risk = float(observation["closing_risk"])

    # Motion is never permitted through an unsafe observation.
    if safety_confidence < 0.60 or closing_risk >= 0.75:
        memory["state"] = "STOPPED"
        return "STOP", 0.99, memory

    confirmed = (
        visible
        and target_confidence >= 0.55
        and identity_confidence >= 0.60
    )

    if not confirmed:
        if state in {"LOCKED", "APPROACH", "REACQUIRE"} or lost_steps > 0:
            memory["state"] = "REACQUIRE"
            if lost_steps <= 1:
                return "STOP", 0.94, memory

        action = scan_direction
        memory["scan_direction"] = (
            "SCAN_RIGHT" if scan_direction == "SCAN_LEFT" else "SCAN_LEFT"
        )
        memory["state"] = "SEARCH"
        return action, 0.75, memory

    # Two-frame tracking remains the normal verification rule. Exceptionally
    # strong independent confidence signals avoid an otherwise redundant hold.
    strongly_verified = (
        target_confidence >= 0.85 and identity_confidence >= 0.90
    )
    if track_age < 2 and not strongly_verified:
        memory["state"] = "VERIFY"
        return "SLOW_DOWN", 0.82, memory

    memory["state"] = "LOCKED"

    if distance == "near":
        heading_error = float(observation["heading_error"])
        if abs(heading_error) <= 15.0 and identity_confidence >= 0.80:
            memory["state"] = "ARRIVED"
            return "ARRIVED", 0.97, memory

        memory["state"] = "APPROACH"
        if bearing < 0.0:
            return "VEER_LEFT", 0.88, memory
        if bearing > 0.0:
            return "VEER_RIGHT", 0.88, memory
        return ("VEER_LEFT" if heading_error < 0.0 else "VEER_RIGHT"), 0.86, memory

    memory["state"] = "APPROACH"
    if bearing < -12.0 and observation["corridor_left"]:
        return "VEER_LEFT", 0.90, memory
    if bearing > 12.0 and observation["corridor_right"]:
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