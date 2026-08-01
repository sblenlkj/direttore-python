from __future__ import annotations

from dataclasses import dataclass

from direttore.core.engines.config import (
    BaseEngineConfig,
    UseCaseEngineConfig,
)
from direttore.core.engines.modular_monolith.modular_monolith_payload_loader import (
    ModularKeyPayloadLoader,
)


@dataclass(frozen=True, slots=True)
class ModularMonolithUseCaseEngineConfig(
    UseCaseEngineConfig,
):
    payload_key_loader: ModularKeyPayloadLoader | None = None


@dataclass(frozen=True, slots=True)
class ModularMonolithQueryEngineConfig(
    BaseEngineConfig,
):
    payload_key_loader: ModularKeyPayloadLoader | None = None
