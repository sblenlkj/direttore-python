from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.application.execution_slot_pool import (
    ExecutionSlotPool,
    ExecutionSlotPoolStats,
)
from direttore.application.simple_service.config import (
    SimpleServiceDirettoreConfig,
)
from direttore.application.simple_service.execution_slot import (
    SimpleServiceExecutionSlot,
)
from direttore.core.contracts.handlers import (
    QueryHandlerResult,
    UseCaseHandlerResult,
)
from direttore.core.contracts.messages import Query, UseCaseCommand
from direttore.core.engines.simple_service.simple_service_query_engine import (
    SimpleServiceQueryEngine,
)
from direttore.core.engines.simple_service.simple_service_use_case_engine import (
    SimpleServiceUseCaseEngine,
)
from direttore.core.event_dispatchers.simple_service_event_dispatcher import (
    SimpleServiceEventDispatcher,
)
from direttore.core.primitives.container import Container
from direttore.core.resolvers.event_handler_resolver import (
    EventHandlerResolver,
)
from direttore.core.resolvers.query_handler_resolver import (
    QueryHandlerResolver,
)
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)


class SimpleServiceDirettoreApplication:
    def __init__(
        self,
        *,
        config: SimpleServiceDirettoreConfig,
        container: Container,
        initial_slot_count: int = 5,
        max_slot_count: int = 20,
    ) -> None:
        self.config = config
        self.container = container

        self.event_dispatcher = self._build_event_dispatcher()
        self.use_case_engine = self._build_use_case_engine()
        self.query_engine = self._build_query_engine()

        self.slot_pool = ExecutionSlotPool[SimpleServiceExecutionSlot](
            slot_factory=self._create_slot,
            initial_slot_count=initial_slot_count,
            max_slot_count=max_slot_count,
        )

    async def handle(
        self,
        command: UseCaseCommand,
        *,
        input: object,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        async with self.slot_pool.acquire() as slot:
            return await slot.handle(
                command=command,
                input=input,
                trace=trace,
            )

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        async with self.slot_pool.acquire() as slot:
            return await slot.handle_by_key(
                key=key,
                payload=payload,
                input=input,
                trace=trace,
            )

    async def handle_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        async with self.slot_pool.acquire() as slot:
            return await slot.handle_operation(
                operation_id=operation_id,
                input=input,
                trace=trace,
            )

    async def handle_query(
        self,
        query: Query,
        *,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Simple service query execution is not configured."
            )

        async with self.slot_pool.acquire() as slot:
            return await slot.handle_query(
                query=query,
                input=input,
                trace=trace,
            )

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Simple service query execution is not configured."
            )

        async with self.slot_pool.acquire() as slot:
            return await slot.handle_query_by_key(
                key=key,
                payload=payload,
                input=input,
                trace=trace,
            )

    async def handle_query_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Simple service query execution is not configured."
            )

        async with self.slot_pool.acquire() as slot:
            return await slot.handle_query_operation(
                operation_id=operation_id,
                input=input,
                trace=trace,
            )

    def validate(self) -> None:
        self.use_case_engine.resolver.validate()

        if self.query_engine is not None:
            self.query_engine.resolver.validate()

        if self.event_dispatcher is not None:
            self.event_dispatcher.validate_event_handlers()

    def slot_pool_stats(self) -> ExecutionSlotPoolStats:
        return self.slot_pool.stats()

    def _build_event_dispatcher(
        self,
    ) -> SimpleServiceEventDispatcher | None:
        if self.config.handlers.event_registry is None:
            return None

        event_resolver = EventHandlerResolver(
            registry=self.config.handlers.event_registry,
            container=self.container,
        )

        return SimpleServiceEventDispatcher(
            resolver=event_resolver,
        )

    def _build_use_case_engine(
        self,
    ) -> SimpleServiceUseCaseEngine:
        use_case_resolver = UseCaseHandlerResolver(
            registry=self.config.handlers.use_case_registry,
            container=self.container,
        )

        return SimpleServiceUseCaseEngine(
            resolver=use_case_resolver,
            event_dispatcher=self.event_dispatcher,
            span_factory=self.config.span_factory,
            config=self.config.use_case_engine,
        )

    def _build_query_engine(
        self,
    ) -> SimpleServiceQueryEngine | None:
        if self.config.handlers.query_registry is None:
            return None

        query_resolver = QueryHandlerResolver(
            registry=self.config.handlers.query_registry,
            container=self.container,
        )

        return SimpleServiceQueryEngine(
            resolver=query_resolver,
            span_factory=self.config.span_factory,
            config=self.config.query_engine,
        )

    def _create_slot(
        self,
    ) -> SimpleServiceExecutionSlot:
        use_case_resource_holder = (
            self.config.slot.use_case_resource_holder_factory()
        )
        use_case_uow = self.config.slot.use_case_uow_factory(
            use_case_resource_holder,
        )

        query_resource_holder = None
        query_uow = None

        if (
            self.config.slot.query_resource_holder_factory is not None
            and self.config.slot.query_uow_factory is not None
        ):
            query_resource_holder = (
                self.config.slot.query_resource_holder_factory()
            )
            query_uow = self.config.slot.query_uow_factory(
                query_resource_holder,
            )

        return SimpleServiceExecutionSlot(
            use_case_engine=self.use_case_engine,
            use_case_resource_holder=use_case_resource_holder,
            use_case_uow=use_case_uow,
            query_engine=self.query_engine,
            query_resource_holder=query_resource_holder,
            query_uow=query_uow,
        )
