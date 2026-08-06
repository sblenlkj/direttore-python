from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import TYPE_CHECKING

from direttore.core.saga.models import SagaEntry, SagaRecord

if TYPE_CHECKING:
    from direttore.core.primitives.resource_holder import ResourceHolder
    from direttore.core.tracing import Span


class SagaNotFoundError(LookupError):
    pass


class SagaJournal(ABC):
    @abstractmethod
    async def save(
        self,
        record: SagaRecord,
        resource: ResourceHolder,
        span: Span | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def load(
        self,
        saga_id: str,
        resource: ResourceHolder,
        span: Span | None,
    ) -> SagaRecord:
        raise NotImplementedError


class InMemorySagaJournal(SagaJournal):
    """Serialization-shaped journal that never stores live compensations."""

    def __init__(self) -> None:
        self._records: dict[str, SagaRecord] = {}

    async def save(
        self,
        record: SagaRecord,
        resource: ResourceHolder,
        span: Span | None,
    ) -> None:
        self._records[record.saga_id] = self._copy_record(record)

    async def load(
        self,
        saga_id: str,
        resource: ResourceHolder,
        span: Span | None,
    ) -> SagaRecord:
        record = self._records.get(saga_id)
        if record is None:
            raise SagaNotFoundError(f"Saga {saga_id!r} was not found.")
        return self._copy_record(record)

    @staticmethod
    def _copy_record(record: SagaRecord) -> SagaRecord:
        return SagaRecord(
            saga_id=record.saga_id,
            entries=tuple(
                SagaEntry(
                    kind=entry.kind,
                    handler_key=entry.handler_key,
                    payload=deepcopy(dict(entry.payload)),
                )
                for entry in record.entries
            ),
        )
