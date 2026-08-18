from benchmarks.math.circle_packing.evaluator import run_with_timeout


def test_run_with_timeout_handles_windows_style_workspace_path(tmp_path):
    candidate_dir = tmp_path / "Users Smoke"
    candidate_dir.mkdir()
    candidate_path = candidate_dir / "candidate.py"
    candidate_path.write_text(
        """\
import numpy as np


def run_packing():
    centers = np.zeros((26, 2))
    radii = np.zeros(26)
    return centers, radii, float(radii.sum())
""",
        encoding="utf-8",
    )

    centers, radii, sum_radii = run_with_timeout(candidate_path, timeout_seconds=10)

    assert centers.shape == (26, 2)
    assert radii.shape == (26,)
    assert sum_radii == 0.0
