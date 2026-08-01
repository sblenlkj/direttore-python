from __future__ import annotations

from dataclasses import dataclass

from direttore.core.engines.config import (
    QueryEngineConfig,
    UseCaseEngineConfig,
)
from direttore.core.engines.simple_service.simple_service_payload_loader import (
    SimpleServiceKeyPayloadLoader,
)


@dataclass(frozen=True, slots=True)
class SimpleServiceUseCaseEngineConfig(
    UseCaseEngineConfig,
):
    payload_key_loader: SimpleServiceKeyPayloadLoader | None = None


@dataclass(frozen=True, slots=True)
class SimpleServiceQueryEngineConfig(
    QueryEngineConfig,
):
    payload_key_loader: SimpleServiceKeyPayloadLoader | None = None