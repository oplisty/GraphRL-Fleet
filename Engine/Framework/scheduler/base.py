from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.simulation import Environment


class SchedulerBase(ABC):
    @abstractmethod
    def select_actions(self, env: Environment) -> list[tuple[int, int] | dict]:
        """Return actions for current step.

        Supported action formats:
        - (vehicle_id, task_id): single-vehicle dispatch
        - {"task_id": int, "vehicle_allocations": {vehicle_id: load, ...}}: collaborative dispatch
        """
        raise NotImplementedError
