from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.primitives.uow import BaseUnitOfWork


@dataclass(frozen=True, slots=True)
class KeyPayloadPair:
    key: str
    payload: Mapping[str, Any]


class SimpleServiceOperationLoader(ABC):
    @abstractmethod
    async def get_key_payload_pair(
        self, operation_id: int | str, uow: BaseUnitOfWork
    ) -> KeyPayloadPair:
        raise NotImplementedError


class ModularMonolithOperationLoader(ABC):
    @abstractmethod
    async def get_key_payload_pair(
        self,
        operation_id: int | str,
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> KeyPayloadPair:
        raise NotImplementedError
