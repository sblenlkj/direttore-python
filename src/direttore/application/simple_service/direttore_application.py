from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any

from direttore.application.simple_service.config import (
    SimpleServiceDirettoreConfig,
)
from direttore.application.simple_service.execution_slot import (
    SimpleServiceExecutionSlot,
)
from direttore.application.slot_lease import SlotLease
from direttore.application.slot_provider import (
    ExecutionSlotProvider,
    ExecutionSlotProviderStats,
    PoolExecutionSlotProvider,
)
from direttore.core.contracts.messages import Query, UseCaseCommand
from direttore.core.event_dispatchers.simple_service_event_dispatcher import (
    SimpleServiceEventDispatcher,
)
from direttore.core.primitives.container import Container
from direttore.core.resolvers.event_handler_resolver import EventHandlerResolver
from direttore.core.resolvers.query_handler_resolver import QueryHandlerResolver
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)

type SimpleSlotProviderFactory = Callable[
    [Callable[[], SimpleServiceExecutionSlot]],
    ExecutionSlotProvider[SimpleServiceExecutionSlot],
]


class SimpleServiceDirettoreApplication:
    """Simple-service Director backed by a configurable slot provider."""

    def __init__(
        self,
        *,
        config: SimpleServiceDirettoreConfig,
        container: Container,
        slot_provider_factory: SimpleSlotProviderFactory | None = None,
        initial_slot_count: int = 5,
        max_slot_count: int = 20,
    ) -> None:
        self.config = config
        self.container = container
        self.use_case_resolver = UseCaseHandlerResolver(
            registry=config.handlers.use_case_registry,
            container=container,
        )
        self.query_resolver = (
            QueryHandlerResolver(
                registry=config.handlers.query_registry,
                container=container,
            )
            if config.handlers.query_registry is not None
            else None
        )
        self.event_dispatcher = self._build_event_dispatcher()
        if slot_provider_factory is None:
            self.slot_provider = PoolExecutionSlotProvider(
                slot_factory=self._create_slot,
                initial_slot_count=initial_slot_count,
                max_slot_count=max_slot_count,
            )
        else:
            self.slot_provider = slot_provider_factory(self._create_slot)

    async def acquire_slot(self, *, saga_id: str | None = None) -> SlotLease:
        return await self.slot_provider.acquire(saga_id=saga_id)

    @asynccontextmanager
    async def slot(self, *, saga_id: str | None = None) -> AsyncGenerator[SlotLease]:
        lease = await self.acquire_slot(saga_id=saga_id)
        try:
            yield lease
        finally:
            await lease.release()

    async def handle(
        self,
        command: UseCaseCommand,
        *,
        input: object,
        trace: object | None = None,
        saga_id: str | None = None,
    ) -> Any:
        async with self.slot(saga_id=saga_id) as lease:
            async with lease.transaction():
                return await lease.handle(command, input=input, trace=trace)

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
        saga_id: str | None = None,
    ) -> Any:
        async with self.slot(saga_id=saga_id) as lease:
            async with lease.transaction():
                return await lease.handle_by_key(key, payload, input=input, trace=trace)

    async def handle_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
        saga_id: str | None = None,
    ) -> Any:
        async with self.slot(saga_id=saga_id) as lease:
            async with lease.transaction():
                return await lease.handle_operation(
                    operation_id, input=input, trace=trace
                )

    async def handle_query(
        self,
        query: Query,
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        async with self.slot() as lease:
            async with lease.transaction():
                return await lease.handle_query(query, input=input, trace=trace)

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        async with self.slot() as lease:
            async with lease.transaction():
                return await lease.handle_query_by_key(
                    key, payload, input=input, trace=trace
                )

    async def handle_query_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        async with self.slot() as lease:
            async with lease.transaction():
                return await lease.handle_query_operation(
                    operation_id, input=input, trace=trace
                )

    async def compensate_saga(
        self,
        saga_id: str,
        *,
        input: object = None,
        trace: object | None = None,
    ) -> None:
        async with self.slot() as lease:
            async with lease.transaction():
                await lease.compensate_saga(saga_id, input=input, trace=trace)

    def validate(self) -> None:
        self.use_case_resolver.validate()
        if self.query_resolver is not None:
            self.query_resolver.validate()
        if self.event_dispatcher is not None:
            self.event_dispatcher.validate_event_handlers()

    def slot_provider_stats(self) -> ExecutionSlotProviderStats:
        return self.slot_provider.stats()

    def slot_pool_stats(self) -> ExecutionSlotProviderStats:
        """Deprecated name for metrics callers migrating to providers."""
        return self.slot_provider_stats()

    def _create_slot(self) -> SimpleServiceExecutionSlot:
        holder = self.config.slot.resource_holder_factory()
        uow = self.config.slot.uow_factory(holder)
        return SimpleServiceExecutionSlot(
            use_case_resolver=self.use_case_resolver,
            query_resolver=self.query_resolver,
            event_dispatcher=self.event_dispatcher,
            resource_holder=holder,
            uow=uow,
            use_case_payload_loader=(self.config.use_case_execution.operation_loader),
            query_payload_loader=self.config.query_execution.operation_loader,
            span_factory=self.config.span_factory,
            saga_journal=self.config.saga_journal,
            max_processed_events=(self.config.use_case_execution.max_processed_events),
        )

    def _build_event_dispatcher(self) -> SimpleServiceEventDispatcher | None:
        if self.config.handlers.event_registry is None:
            return None
        return SimpleServiceEventDispatcher(
            resolver=EventHandlerResolver(
                registry=self.config.handlers.event_registry,
                container=self.container,
            )
        )
