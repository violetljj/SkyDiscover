# EVOLVE-BLOCK-START
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from skydiscover.config import DatabaseConfig
from skydiscover.search.base_database import Program, ProgramDatabase

logger = logging.getLogger(__name__)


@dataclass
class EvolvedProgram(Program):
    """Program representation required by EvoX migration."""


class EvolvedProgramDatabase(ProgramDatabase):
    """Frozen Sky best-of-three initial routing for the COMP-2 hybrid arm."""

    BEST_OF_N = 3

    def __init__(self, name: str, config: DatabaseConfig):
        super().__init__(name, config)
        self.current_parent_id: Optional[str] = None
        self.parent_additions = 0

    def add(self, program: EvolvedProgram, iteration: Optional[int] = None, **kwargs) -> str:
        self.programs[program.id] = program
        if iteration is not None:
            self.last_iteration = max(self.last_iteration, iteration)
        if self.current_parent_id is not None and program.iteration_found > 0:
            self.parent_additions += 1
        if self.config.db_path:
            self._save_program(program)
        self._update_best_program(program)
        return program.id

    @staticmethod
    def _score(program: EvolvedProgram) -> float:
        score = program.metrics.get("combined_score") if program.metrics else None
        return float(score) if isinstance(score, (int, float)) else float("-inf")

    def sample(
        self, num_context_programs: Optional[int] = 4, **kwargs
    ) -> Tuple[Dict[str, EvolvedProgram], Dict[str, List[EvolvedProgram]]]:
        if not self.programs:
            raise ValueError("No candidates available for sampling")
        if (
            self.current_parent_id is None
            or self.current_parent_id not in self.programs
            or self.parent_additions >= self.BEST_OF_N
        ):
            parent = max(self.programs.values(), key=self._score)
            self.current_parent_id = parent.id
            self.parent_additions = 0
        else:
            parent = self.programs[self.current_parent_id]

        count = max(0, int(num_context_programs or 0))
        context = sorted(
            (program for program in self.programs.values() if program.id != parent.id),
            key=self._score,
            reverse=True,
        )[:count]
        return {"": parent}, {"": context}


# EVOLVE-BLOCK-END
