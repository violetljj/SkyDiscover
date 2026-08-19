"""Searchable policy units with explicit temporal and termination contracts."""

MOVES = {"FORWARD", "VEER_LEFT", "VEER_RIGHT"}


def safety_contract(observation):
    """Return the mandatory safe fallback, or allow policy evaluation."""
    if observation["safety_confidence"] < 0.60 or observation["closing_risk"] >= 0.75:
        return "STOP", 0.99
    return None


def tracking_contract(observation, memory):
    """Verify a target and perform bounded reacquisition while motion is withheld."""
    visible = bool(observation["target_visible"])
    reliable = (
        visible
        and observation["target_confidence"] >= 0.55
        and observation["target_identity_confidence"] >= 0.60
    )
    if not reliable:
        lost_steps = int(observation["lost_steps"])
        state = memory.get("state", "IDLE")
        memory["state"] = "REACQUIRE"
        if state in {"LOCKED", "APPROACH", "REACQUIRE"} and lost_steps <= 1:
            return "STOP", 0.92
        direction = memory.get("scan_direction", "SCAN_LEFT")
        ticks = int(memory.get("scan_ticks", 0))
        if ticks >= 2:
            direction = "SCAN_RIGHT" if direction == "SCAN_LEFT" else "SCAN_LEFT"
            ticks = 0
        memory.update(scan_direction=direction, scan_ticks=ticks + 1, state="SEARCH")
        return direction, 0.75
    if observation["track_age"] < 2:
        memory["state"] = "VERIFY"
        return "SLOW_DOWN", 0.80
    return None


def propose_moves(observation):
    """Return ordered observable movement units without hidden topology assumptions."""
    bearing = float(observation["target_bearing"])
    left = bool(observation["corridor_left"])
    center = bool(observation["corridor_center"])
    right = bool(observation["corridor_right"])
    candidates = []
    if bearing < -8.0 and left:
        candidates.append("VEER_LEFT")
    if bearing > 8.0 and right:
        candidates.append("VEER_RIGHT")
    if center:
        candidates.append("FORWARD")
    if left:
        candidates.append("VEER_LEFT")
    if right:
        candidates.append("VEER_RIGHT")
    return list(dict.fromkeys(candidates))


def progress_contract(observation, memory, candidates):
    """Reject failed moves at one progress level and terminate when choices are exhausted."""
    progress = float(observation["progress"])
    previous_progress = memory.get("last_move_progress")
    if previous_progress is None or progress > float(previous_progress) + 1e-9:
        memory["failed_moves"] = []
    elif memory.get("last_move") in MOVES:
        failed = list(memory.get("failed_moves", []))
        if memory["last_move"] not in failed:
            failed.append(memory["last_move"])
        memory["failed_moves"] = failed
    failed = set(memory.get("failed_moves", []))
    return next((candidate for candidate in candidates if candidate not in failed), None)


def decide(observation, memory):
    """Compose safety, tracking, proposal, progress, and termination units."""
    memory = dict(memory or {})
    fallback = safety_contract(observation)
    if fallback:
        memory["state"] = "STOPPED"
        return *fallback, memory

    tracking = tracking_contract(observation, memory)
    if tracking:
        return *tracking, memory

    progress = float(observation["progress"])
    bearing = float(observation["target_bearing"])
    memory["state"] = "LOCKED"
    if observation["target_distance_class"] == "near":
        if (
            abs(float(observation["heading_error"])) <= 15.0
            and observation["target_identity_confidence"] >= 0.80
        ):
            memory["state"] = "ARRIVED"
            return "ARRIVED", 0.96, memory
        candidates = ["VEER_LEFT" if bearing < 0.0 else "VEER_RIGHT"]
    else:
        candidates = propose_moves(observation)

    action = progress_contract(observation, memory, candidates)
    if action is None:
        # TERMINATION_CONTRACT
        memory["state"] = "STOPPED"
        return "STOP", 0.98, memory
    memory.update(state="APPROACH", last_move=action, last_move_progress=progress)
    return action, 0.90 if action == candidates[0] else 0.82, memory
