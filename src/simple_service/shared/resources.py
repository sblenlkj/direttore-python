from inspect import isawaitable
from typing import cast

from direttore import KeyPayloadPair, OperationLoader, ResourceHolder
from direttore.core.tracing import Span
from simple_service.adapters.outbound.in_memory.database import InMemorySession


class ExampleResourceHolder(ResourceHolder):
    async def commit(self) -> None:
        self._ensure_not_finalized()
        for name, resource in self._resources.items():
            method = resource.commit if self._commit_required[name] else resource.rollback
            result = method()
            if isawaitable(result):
                await result
        self._mark_finalized()

    async def rollback(self) -> None:
        if self.is_finalized:
            return
        for resource in self._resources.values():
            result = resource.rollback()
            if isawaitable(result):
                await result
        self._mark_finalized()

    async def close(self) -> None:
        for resource in reversed(tuple(self._resources.values())):
            result = resource.close()
            if isawaitable(result):
                await result


class InMemoryOperationLoader(OperationLoader):
    async def get_key_payload_pair(
        self,
        operation_id: int | str,
        resource: ResourceHolder,
        span: Span | None,
    ) -> KeyPayloadPair:
        session = cast(InMemorySession, await resource.get_session("primary"))
        session.record_access("operations.get")
        key, payload = session.operations[str(operation_id)]
        return KeyPayloadPair(key=key, payload=payload)

