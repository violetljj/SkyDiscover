import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks" / "blindassist_last10m_structured_direct_1"
sys.path.insert(0, str(BENCHMARK))

from autopsy import analyze  # noqa: E402


def test_structured_autopsy_is_receipt_only_and_descriptive():
    result = analyze(
        BENCHMARK / "receipts" / "execution",
        BENCHMARK / "structured_initial_program.py",
    )
    assert result["fresh_tasks"] == 0
    assert result["model_calls"] == 0
    assert result["receipt_only"] is True
    assert result["instance_count"] == 12
    assert result["paired_summary"]["structured_robust_safe"] == 10
    assert result["paired_summary"]["wins"] == 2
    assert result["paired_summary"]["losses"] == 1
    assert "causal" in result["claim_ceiling"]
