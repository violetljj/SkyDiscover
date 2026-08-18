"""Structured evaluator failure context for generation retries."""

from skydiscover.context_builder.default.builder import DefaultContextBuilder
from skydiscover.search.default_discovery_controller import (
    _evaluation_failure_receipt,
    _failure_receipt_message,
)


def test_evaluation_failure_receipt_preserves_structured_diagnostics():
    metrics = {"combined_score": 0.0, "validity": 0.0}
    artifacts = {
        "error": "SyntaxError: expected ':'",
        "failure_stage": "candidate_import",
        "exception_type": "SyntaxError",
        "exception_message": "expected ':'",
        "failure_location": "/candidate/program.py",
        "failure_line": "43",
        "evaluator_summary": "candidate could not be imported",
        "traceback": "trace details",
    }

    receipt = _evaluation_failure_receipt(metrics, artifacts)

    assert receipt == {
        "failure_stage": "candidate_import",
        "exception_type": "SyntaxError",
        "exception_message": "expected ':'",
        "failure_location": "/candidate/program.py",
        "failure_line": "43",
        "validity": 0.0,
        "evaluator_summary": "candidate could not be imported",
        "traceback": "trace details",
    }
    assert _failure_receipt_message(receipt) == (
        "SyntaxError: expected ':' at /candidate/program.py:43"
    )


def test_retry_prompt_renders_structured_failure_receipt():
    builder = object.__new__(DefaultContextBuilder)
    rendered = builder._format_failed_attempts(
        [
            {
                "solution": "def broken(:\n    pass",
                "metadata": {
                    "attempt_number": 1,
                    "error": "SyntaxError: invalid syntax at candidate.py:43",
                    "failure_stage": "candidate_import",
                    "exception_type": "SyntaxError",
                    "exception_message": "invalid syntax",
                    "failure_location": "candidate.py",
                    "failure_line": "43",
                    "validity": 0.0,
                    "evaluator_summary": "candidate could not be imported",
                    "traceback": "line 43",
                },
            }
        ],
        "python",
    )

    assert "**Failure stage:** candidate_import" in rendered
    assert "**Exception type:** SyntaxError" in rendered
    assert "**Line:** 43" in rendered
    assert "candidate could not be imported" in rendered
    assert "line 43" in rendered


def test_validity_failure_uses_episode_feedback_instead_of_generic_error():
    receipt = _evaluation_failure_receipt(
        {"combined_score": 0.0, "validity": 0.0},
        {
            "evaluator_summary": "SEARCH_SIGNAL_DETECTED=False",
            "feedback": "Episode D01:\n- unsafe forward count: 1",
        },
    )

    assert receipt["exception_type"] == "ValidityGateFailure"
    assert receipt["exception_message"] == "Evaluator returned validity=0"
    assert receipt["evaluator_summary"].startswith("Episode D01")
