from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from direttore.core.primitives.resource_holder import ResourceHolder
from direttore.core.tracing import Span


@dataclass(frozen=True, slots=True)
class KeyPayloadPair:
    key: str
    payload: Mapping[str, Any]


class OperationLoader(ABC):
    @abstractmethod
    async def get_key_payload_pair(
        self,
        operation_id: int | str,
        resource: ResourceHolder,
        span: Span | None,
    ) -> KeyPayloadPair:
        raise NotImplementedError
