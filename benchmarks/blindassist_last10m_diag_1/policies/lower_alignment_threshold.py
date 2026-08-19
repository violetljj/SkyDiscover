"""Hand-written reachability probe for L10M-DIAG-1."""


def decide(observation, memory):
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

    if safety_confidence < 0.60 or closing_risk >= 0.75:
        memory["state"] = "STOPPED"
        return "STOP", 0.99, memory
    if not visible or target_confidence < 0.55 or identity_confidence < 0.60:
        if state in {"LOCKED", "APPROACH", "REACQUIRE"} or lost_steps > 0:
            memory["state"] = "REACQUIRE"
            if lost_steps <= 1:
                return "STOP", 0.92, memory
        memory["scan_direction"] = "SCAN_RIGHT" if scan_direction == "SCAN_LEFT" else "SCAN_LEFT"
        memory["state"] = "SEARCH"
        return scan_direction, 0.75, memory
    if track_age < 2:
        memory["state"] = "VERIFY"
        return "SLOW_DOWN", 0.80, memory
    memory["state"] = "LOCKED"
    if distance == "near":
        if abs(float(observation["heading_error"])) <= 15.0 and identity_confidence >= 0.80:
            memory["state"] = "ARRIVED"
            return "ARRIVED", 0.96, memory
        return ("VEER_LEFT" if bearing < 0 else "VEER_RIGHT"), 0.88, memory
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
