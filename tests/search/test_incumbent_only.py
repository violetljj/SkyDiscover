"""Tests for the archive-free incumbent-only comparison control."""

from skydiscover.config import DatabaseConfig
from skydiscover.search.base_database import Program
from skydiscover.search.incumbent_only.database import IncumbentOnlyDatabase


def _program(program_id: str, score: float, iteration: int) -> Program:
    return Program(
        id=program_id,
        solution=f"# {program_id}",
        language="python",
        metrics={"combined_score": score},
        iteration_found=iteration,
    )


def test_incumbent_only_exposes_best_program_without_archive_context():
    database = IncumbentOnlyDatabase("incumbent_only", DatabaseConfig())
    database.add(_program("seed", 0.4, 0), iteration=0)
    database.add(_program("weaker", 0.3, 1), iteration=1)
    database.add(_program("best", 0.8, 2), iteration=2)

    parent, context = database.sample(num_context_programs=99)

    assert parent.id == "best"
    assert context == []
