from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SagaHandlerKind(StrEnum):
    USE_CASE = "use_case"
    EVENT = "event"


@dataclass(frozen=True, slots=True)
class SagaEntry:
    kind: SagaHandlerKind
    handler_key: str
    payload: Mapping[str, Any]

    def copy(self) -> SagaEntry:
        return SagaEntry(
            kind=self.kind,
            handler_key=self.handler_key,
            payload=deepcopy(dict(self.payload)),
        )


@dataclass(frozen=True, slots=True)
class SagaRecord:
    saga_id: str
    entries: tuple[SagaEntry, ...]


@dataclass(frozen=True, slots=True)
class SagaCompensationContext[UnitOfWorkT, SpanT]:
    saga_id: str
    uow: UnitOfWorkT
    span: SpanT | None
