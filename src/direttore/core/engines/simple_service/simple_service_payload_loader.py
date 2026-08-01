from typing import Any

from direttore.core.engines.key_payload_pair import KeyPayloadPair
from direttore.core.primitives.uow import BaseUnitOfWork

class SimpleServiceKeyPayloadLoader:
    async def get_key_payload_pair(
        self,
        operation_id: Any,
        uow: BaseUnitOfWork,
    ) -> KeyPayloadPair:
        raise NotImplementedError
