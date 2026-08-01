from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.application.base_execution_slot import BaseExecutionSlot
from direttore.core.contracts.handlers import (
    QueryHandlerResult,
    UseCaseHandlerResult,
)
from direttore.core.contracts.messages import Query, UseCaseCommand
from direttore.core.engines.modular_monolith.modular_monolith_query_engine import (
    ModularMonolithQueryEngine,
)
from direttore.core.engines.modular_monolith.modular_monolith_use_case_engine import (
    ModularMonolithUseCaseEngine,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import (
    AbstractUseCaseResourceHolder,
    QueryResourceHolder,
)


class ModularMonolithExecutionSlot(BaseExecutionSlot):
    def __init__(
        self,
        *,
        use_case_engine: ModularMonolithUseCaseEngine,
        use_case_resource_holder: AbstractUseCaseResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
        query_engine: ModularMonolithQueryEngine | None = None,
        query_resource_holder: QueryResourceHolder | None = None,
    ) -> None:
        if query_engine is None and query_resource_holder is not None:
            raise ValueError(
                "query_resource_holder was provided without query_engine."
            )

        if query_engine is not None and query_resource_holder is None:
            raise ValueError(
                "query_engine requires query_resource_holder."
            )

        self.use_case_engine = use_case_engine
        self.query_engine = query_engine

        self.use_case_resource_holder = use_case_resource_holder
        self.query_resource_holder = query_resource_holder

        self.coordinator = coordinator
        self.runtime = runtime
        self.event_queue = event_queue

    async def handle(
        self,
        *,
        command: UseCaseCommand,
        input: object,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        return await self.use_case_engine.handle(
            command=command,
            input=input,
            resource_holder=self.use_case_resource_holder,
            coordinator=self.coordinator,
            runtime=self.runtime,
            event_queue=self.event_queue,
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
        return await self.use_case_engine.handle_by_key(
            key=key,
            payload=payload,
            input=input,
            resource_holder=self.use_case_resource_holder,
            coordinator=self.coordinator,
            runtime=self.runtime,
            event_queue=self.event_queue,
            trace=trace,
        )

    async def handle_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        return await self.use_case_engine.handle_operation(
            operation_id=operation_id,
            input=input,
            resource_holder=self.use_case_resource_holder,
            coordinator=self.coordinator,
            runtime=self.runtime,
            event_queue=self.event_queue,
            trace=trace,
        )

    async def handle_query(
        self,
        *,
        query: Query,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        query_engine, query_resource_holder = (
            self._require_query_execution()
        )

        return await query_engine.handle(
            query=query,
            input=input,
            resource_holder=query_resource_holder,
            coordinator=self.coordinator,
            runtime=self.runtime,
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
        query_engine, query_resource_holder = (
            self._require_query_execution()
        )

        return await query_engine.handle_by_key(
            key=key,
            payload=payload,
            input=input,
            resource_holder=query_resource_holder,
            coordinator=self.coordinator,
            runtime=self.runtime,
            trace=trace,
        )

    async def handle_query_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        query_engine, query_resource_holder = (
            self._require_query_execution()
        )

        return await query_engine.handle_operation(
            operation_id=operation_id,
            input=input,
            resource_holder=query_resource_holder,
            coordinator=self.coordinator,
            runtime=self.runtime,
            trace=trace,
        )

    def reset(self) -> None:
        self.runtime._set_lifecycle_context(None)
        self.event_queue.clear()

    def _require_query_execution(
        self,
    ) -> tuple[
        ModularMonolithQueryEngine,
        QueryResourceHolder,
    ]:
        if (
            self.query_engine is None
            or self.query_resource_holder is None
        ):
            raise RuntimeError(
                "Modular monolith query execution is not configured."
            )

        return (
            self.query_engine,
            self.query_resource_holder,
        )
