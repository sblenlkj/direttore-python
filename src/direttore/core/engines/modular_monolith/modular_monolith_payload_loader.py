from typing import Any

from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.engines.key_payload_pair import KeyPayloadPair

class ModularKeyPayloadLoader:
    async def get_key_payload_pair(
        self,
        operation_id: Any,
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> KeyPayloadPair:
        raise NotImplementedError
