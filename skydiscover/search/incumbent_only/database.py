"""Minimal incumbent-only database for strong naked-model controls."""

from __future__ import annotations

from typing import List, Optional, Tuple

from skydiscover.config import DatabaseConfig
from skydiscover.search.base_database import Program, ProgramDatabase


class IncumbentOnlyDatabase(ProgramDatabase):
    """Always expose only the current best program and never an archive context."""

    def __init__(self, name: str, config: DatabaseConfig):
        super().__init__(name, config)

    def add(self, program: Program, iteration: Optional[int] = None, **kwargs) -> str:
        self.programs[program.id] = program
        if iteration is not None:
            self.last_iteration = max(self.last_iteration, iteration)
        if self.config.db_path:
            self._save_program(program)
        self._update_best_program(program)
        return program.id

    def sample(
        self, num_context_programs: Optional[int] = 0, **kwargs
    ) -> Tuple[Program, List[Program]]:
        if not self.programs:
            raise ValueError("Cannot sample: no programs in database")
        incumbent = self.get_best_program()
        if incumbent is None:
            raise ValueError("Cannot sample: no valid incumbent")
        return incumbent, []
