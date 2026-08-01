from __future__ import annotations

from abc import ABC, abstractmethod

class BaseExecutionSlot(ABC):
    @abstractmethod
    def reset(self) -> None:
        """Reset slot execution state before returning it to the slot pool.

        Slot-owned long-lived objects should not be destroyed here.

        Typical reset work:

            - clear event queue;
            - clear runtime auth/trace/span state;
            - clear other per-execution metadata.

        Resource cleanup itself belongs to ResourceHolder lifecycle.
        """

        raise NotImplementedError