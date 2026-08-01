from __future__ import annotations

from abc import ABC, abstractmethod

from direttore.core.primitives.resource_holder import ResourceHolder
from direttore.core.saga import SagaJournal, SagaRecord


class BaseExecutionSlot(ABC):
    """Reusable physical container for one lease at a time."""

    def __init__(
        self,
        *,
        resource_holder: ResourceHolder,
        saga_journal: SagaJournal | None = None,
    ) -> None:
        self.resource_holder = resource_holder
        self.saga_journal = saga_journal
        self.generation = 0
        self._leased = False
        self._saga_id: str | None = None

    @property
    def is_leased(self) -> bool:
        return self._leased

    @property
    def saga_id(self) -> str | None:
        return self._saga_id

    async def start_lease(self, *, saga_id: str | None = None) -> int:
        if self._leased:
            raise RuntimeError("Execution slot is already leased.")
        self.generation += 1
        self._leased = True
        self._saga_id = saga_id
        try:
            await self.resource_holder.open()
        except BaseException:
            self._leased = False
            self._saga_id = None
            raise
        return self.generation

    async def commit(self) -> None:
        self._ensure_leased()
        await self._persist_saga_entries()
        await self.resource_holder.commit()
        await self.after_transaction_commit()

    async def rollback(self) -> None:
        self._ensure_leased()
        await self.resource_holder.rollback()

    async def finish_lease(self) -> None:
        try:
            if self.resource_holder.is_open and not self.resource_holder.is_finalized:
                await self.resource_holder.rollback()
        finally:
            try:
                if self.resource_holder.is_open:
                    await self.resource_holder.close()
            finally:
                try:
                    await self.finish_trace()
                finally:
                    self.reset()
                    self._saga_id = None
                    self._leased = False

    async def _persist_saga_entries(self) -> None:
        entries = self.resource_holder.saga_entries
        if not entries:
            return
        if self._saga_id is None:
            self.resource_holder.clear_saga_entries()
            return
        if self.saga_journal is None:
            raise RuntimeError(
                "Saga entries were collected but no SagaJournal is configured."
            )
        await self.saga_journal.save(
            SagaRecord(saga_id=self._saga_id, entries=entries),
            self.resource_holder,
        )

    async def after_transaction_commit(self) -> None:
        """Run work that has its own boundary after the primary commit."""

    async def finish_trace(self) -> None:
        """Finish optional lease-scoped tracing after all cleanup."""

    def _ensure_leased(self) -> None:
        if not self._leased:
            raise RuntimeError("Execution slot is not leased.")

    @abstractmethod
    def reset(self) -> None:
        """Clear all execution-local state before reuse."""
