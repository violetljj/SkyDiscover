#!/usr/bin/env python3
"""Create the one-shot L10M-COMP-1 hidden-v4 split from a fixed seed."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SEED = 40419


def _shortcut(index: int, bearing: int, side: int) -> dict:
    signed_bearing = bearing * side
    action = "VEER_RIGHT" if side > 0 else "VEER_LEFT"
    return {
        "id": f"H4_{index:02d}_route_{'right' if side > 0 else 'left'}_{bearing}",
        "start": "s0",
        "goal_target_id": "goal",
        "max_steps": 12,
        "optimal_movement_steps": 1,
        "node_defaults": {
            "target_visible": True,
            "target_bearing": signed_bearing,
            "target_distance_class": "medium",
            "target_confidence": 0.93,
            "target_identity_confidence": 0.95,
            "corridor_left": True,
            "corridor_center": True,
            "corridor_right": True,
            "closing_risk": 0.03,
            "safety_confidence": 0.98,
            "heading_error": signed_bearing,
            "progress": 0.36,
            "truth_target_id": "goal",
            "transitions": {},
        },
        "nodes": [
            {"id": "s0", "transitions": {action: "goal", "FORWARD": "detour"}},
            {
                "id": "detour",
                "target_bearing": signed_bearing / 2,
                "heading_error": signed_bearing / 2,
                "progress": 0.68,
                "transitions": {"FORWARD": "goal", action: "goal"},
            },
            {
                "id": "goal",
                "target_bearing": 0,
                "target_distance_class": "near",
                "heading_error": 0,
                "progress": 1.0,
                "arrival_valid": True,
            },
        ],
    }


def build_hidden_v4() -> list[dict]:
    """Build a balanced split without consulting any candidate policy."""
    rng = random.Random(SEED)
    bearings = rng.sample([7, 9, 11, 13, 15, 17], 4)
    sides = [-1, 1, -1, 1]
    scenarios = [
        _shortcut(index, bearing, side)
        for index, (bearing, side) in enumerate(zip(bearings, sides), start=1)
    ]
    scenarios.extend(
        [
            {
                "id": "H4_05_left_then_occlusion",
                "start": "s0",
                "goal_target_id": "goal",
                "max_steps": 16,
                "optimal_movement_steps": 3,
                "node_defaults": {
                    "target_visible": True,
                    "target_bearing": -24,
                    "target_distance_class": "far",
                    "target_confidence": 0.94,
                    "target_identity_confidence": 0.96,
                    "corridor_left": True,
                    "corridor_center": True,
                    "corridor_right": True,
                    "closing_risk": 0.04,
                    "safety_confidence": 0.98,
                    "heading_error": -24,
                    "progress": 0.0,
                    "truth_target_id": "goal",
                    "transitions": {},
                },
                "nodes": [
                    {"id": "s0", "transitions": {"VEER_LEFT": "lost"}},
                    {
                        "id": "lost",
                        "target_visible": False,
                        "target_confidence": 0.0,
                        "target_identity_confidence": 0.0,
                        "truth_target_id": None,
                        "progress": 0.3,
                        "transitions": {
                            "STOP": "reacquired",
                            "SCAN_LEFT": "reacquired",
                            "SCAN_RIGHT": "reacquired",
                            "FORWARD": "hazard",
                        },
                    },
                    {
                        "id": "reacquired",
                        "target_bearing": 6,
                        "target_distance_class": "medium",
                        "heading_error": 6,
                        "progress": 0.45,
                        "transitions": {"FORWARD": "mid"},
                    },
                    {
                        "id": "mid",
                        "target_bearing": 2,
                        "target_distance_class": "medium",
                        "heading_error": 2,
                        "progress": 0.72,
                        "transitions": {"FORWARD": "goal"},
                    },
                    {
                        "id": "goal",
                        "target_bearing": 0,
                        "target_distance_class": "near",
                        "heading_error": 0,
                        "progress": 1.0,
                        "arrival_valid": True,
                    },
                    {
                        "id": "hazard",
                        "target_visible": False,
                        "target_confidence": 0.0,
                        "target_identity_confidence": 0.0,
                        "truth_target_id": None,
                        "closing_risk": 0.96,
                        "safety_confidence": 0.2,
                        "progress": 0.05,
                    },
                ],
            },
            {
                "id": "H4_06_closing_risk_clearance",
                "start": "s0",
                "goal_target_id": "goal",
                "max_steps": 14,
                "optimal_movement_steps": 2,
                "node_defaults": {
                    "target_visible": True,
                    "target_bearing": 2,
                    "target_distance_class": "far",
                    "target_confidence": 0.95,
                    "target_identity_confidence": 0.97,
                    "corridor_left": True,
                    "corridor_center": True,
                    "corridor_right": True,
                    "closing_risk": 0.03,
                    "safety_confidence": 0.98,
                    "heading_error": 2,
                    "progress": 0.0,
                    "truth_target_id": "goal",
                    "transitions": {},
                },
                "nodes": [
                    {"id": "s0", "transitions": {"FORWARD": "blocked"}},
                    {
                        "id": "blocked",
                        "target_distance_class": "medium",
                        "closing_risk": 0.79,
                        "progress": 0.48,
                        "transitions": {
                            "STOP": "clear",
                            "SLOW_DOWN": "clear",
                            "FORWARD": "hazard",
                            "VEER_LEFT": "hazard",
                            "VEER_RIGHT": "hazard",
                        },
                    },
                    {
                        "id": "clear",
                        "target_distance_class": "medium",
                        "closing_risk": 0.03,
                        "progress": 0.48,
                        "transitions": {"FORWARD": "goal"},
                    },
                    {
                        "id": "goal",
                        "target_bearing": 0,
                        "target_distance_class": "near",
                        "heading_error": 0,
                        "progress": 1.0,
                        "arrival_valid": True,
                    },
                    {
                        "id": "hazard",
                        "closing_risk": 0.98,
                        "safety_confidence": 0.1,
                        "progress": 0.2,
                    },
                ],
            },
            {
                "id": "H4_07_right_scan_identity_decoy",
                "start": "s0",
                "goal_target_id": "goal",
                "max_steps": 16,
                "optimal_movement_steps": 2,
                "node_defaults": {
                    "target_visible": False,
                    "target_bearing": 0,
                    "target_distance_class": "far",
                    "target_confidence": 0.0,
                    "target_identity_confidence": 0.0,
                    "corridor_left": True,
                    "corridor_center": True,
                    "corridor_right": True,
                    "closing_risk": 0.04,
                    "safety_confidence": 0.98,
                    "heading_error": 0,
                    "progress": 0.0,
                    "truth_target_id": None,
                    "transitions": {},
                },
                "nodes": [
                    {
                        "id": "s0",
                        "transitions": {"SCAN_LEFT": "empty", "SCAN_RIGHT": "decoy"},
                    },
                    {"id": "empty", "transitions": {"SCAN_RIGHT": "decoy"}},
                    {
                        "id": "decoy",
                        "target_visible": True,
                        "target_bearing": 16,
                        "target_confidence": 0.91,
                        "target_identity_confidence": 0.46,
                        "truth_target_id": "decoy",
                        "transitions": {"SCAN_LEFT": "goal0", "VEER_RIGHT": "wrong"},
                    },
                    {
                        "id": "goal0",
                        "target_visible": True,
                        "target_bearing": -21,
                        "target_confidence": 0.95,
                        "target_identity_confidence": 0.97,
                        "truth_target_id": "goal",
                        "heading_error": -21,
                        "transitions": {"VEER_LEFT": "goal1"},
                    },
                    {
                        "id": "goal1",
                        "target_visible": True,
                        "target_bearing": -3,
                        "target_distance_class": "medium",
                        "target_confidence": 0.97,
                        "target_identity_confidence": 0.98,
                        "truth_target_id": "goal",
                        "heading_error": -3,
                        "progress": 0.58,
                        "transitions": {"FORWARD": "goal"},
                    },
                    {
                        "id": "goal",
                        "target_visible": True,
                        "target_bearing": 0,
                        "target_distance_class": "near",
                        "target_confidence": 0.99,
                        "target_identity_confidence": 0.99,
                        "truth_target_id": "goal",
                        "heading_error": 0,
                        "progress": 1.0,
                        "arrival_valid": True,
                    },
                    {
                        "id": "wrong",
                        "target_visible": True,
                        "target_distance_class": "near",
                        "target_identity_confidence": 0.52,
                        "truth_target_id": "decoy",
                        "progress": 0.1,
                    },
                ],
            },
            {
                "id": "H4_08_constrained_right_detour",
                "start": "s0",
                "goal_target_id": "goal",
                "max_steps": 14,
                "optimal_movement_steps": 3,
                "node_defaults": {
                    "target_visible": True,
                    "target_bearing": 5,
                    "target_distance_class": "far",
                    "target_confidence": 0.94,
                    "target_identity_confidence": 0.96,
                    "corridor_left": False,
                    "corridor_center": False,
                    "corridor_right": True,
                    "closing_risk": 0.51,
                    "safety_confidence": 0.93,
                    "heading_error": 5,
                    "progress": 0.0,
                    "truth_target_id": "goal",
                    "transitions": {},
                },
                "nodes": [
                    {"id": "s0", "transitions": {"VEER_RIGHT": "turn"}},
                    {
                        "id": "turn",
                        "target_bearing": -7,
                        "target_distance_class": "medium",
                        "corridor_left": True,
                        "corridor_center": True,
                        "heading_error": -7,
                        "progress": 0.35,
                        "transitions": {"FORWARD": "mid"},
                    },
                    {
                        "id": "mid",
                        "target_bearing": 1,
                        "target_distance_class": "medium",
                        "corridor_center": True,
                        "closing_risk": 0.03,
                        "heading_error": 1,
                        "progress": 0.7,
                        "transitions": {"FORWARD": "goal"},
                    },
                    {
                        "id": "goal",
                        "target_bearing": 0,
                        "target_distance_class": "near",
                        "closing_risk": 0.02,
                        "heading_error": 0,
                        "progress": 1.0,
                        "arrival_valid": True,
                    },
                ],
            },
        ]
    )
    return scenarios


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(build_hidden_v4(), handle, indent=2)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
