from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy

from direttore.core.saga.models import SagaEntry, SagaRecord


class SagaNotFoundError(LookupError):
    pass


class SagaJournal(ABC):
    @abstractmethod
    async def save(self, record: SagaRecord, resource: object) -> None:
        raise NotImplementedError

    @abstractmethod
    async def load(self, saga_id: str, resource: object) -> SagaRecord:
        raise NotImplementedError


class InMemorySagaJournal(SagaJournal):
    """Serialization-shaped journal that never stores live compensations."""

    def __init__(self) -> None:
        self._records: dict[str, SagaRecord] = {}

    async def save(self, record: SagaRecord, resource: object) -> None:
        self._records[record.saga_id] = self._copy_record(record)

    async def load(self, saga_id: str, resource: object) -> SagaRecord:
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
