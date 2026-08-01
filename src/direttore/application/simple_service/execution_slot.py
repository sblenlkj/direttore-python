from __future__ import annotations

from collections.abc import Mapping

from direttore.application.base_execution_slot import BaseExecutionSlot
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
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import (
    AbstractUseCaseResourceHolder,
    QueryResourceHolder,
)
from direttore.core.primitives.uow import BaseUnitOfWork


class SimpleServiceExecutionSlot(BaseExecutionSlot):
    def __init__(
        self,
        *,
        use_case_engine: SimpleServiceUseCaseEngine,
        use_case_resource_holder: AbstractUseCaseResourceHolder,
        use_case_uow: BaseUnitOfWork,
        query_engine: SimpleServiceQueryEngine | None = None,
        query_resource_holder: QueryResourceHolder | None = None,
        query_uow: BaseUnitOfWork | None = None,
    ) -> None:
        has_query_resource_holder = query_resource_holder is not None
        has_query_uow = query_uow is not None

        if has_query_resource_holder != has_query_uow:
            raise ValueError(
                "Query slot resources are incomplete. "
                "Both query_resource_holder and query_uow must be "
                "provided together."
            )

        if query_engine is None and has_query_resource_holder:
            raise ValueError(
                "Query slot resources were provided without "
                "query_engine."
            )

        if query_engine is not None and not has_query_resource_holder:
            raise ValueError(
                "query_engine requires query_resource_holder and "
                "query_uow."
            )

        self.use_case_engine = use_case_engine
        self.query_engine = query_engine

        self.use_case_resource_holder = use_case_resource_holder
        self.use_case_uow = use_case_uow

        self.query_resource_holder = query_resource_holder
        self.query_uow = query_uow

        self.event_queue = EventQueue()

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
            uow=self.use_case_uow,
            event_queue=self.event_queue,
            trace=trace,
        )

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, object],
        *,
        input: object,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        return await self.use_case_engine.handle_by_key(
            key=key,
            payload=payload,
            input=input,
            resource_holder=self.use_case_resource_holder,
            uow=self.use_case_uow,
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
            uow=self.use_case_uow,
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
        query_engine, query_resource_holder, query_uow = (
            self._require_query_execution()
        )

        return await query_engine.handle(
            query=query,
            input=input,
            resource_holder=query_resource_holder,
            uow=query_uow,
            trace=trace,
        )

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, object],
        *,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        query_engine, query_resource_holder, query_uow = (
            self._require_query_execution()
        )

        return await query_engine.handle_by_key(
            key=key,
            payload=payload,
            input=input,
            resource_holder=query_resource_holder,
            uow=query_uow,
            trace=trace,
        )

    async def handle_query_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        query_engine, query_resource_holder, query_uow = (
            self._require_query_execution()
        )

        return await query_engine.handle_operation(
            operation_id=operation_id,
            input=input,
            resource_holder=query_resource_holder,
            uow=query_uow,
            trace=trace,
        )

    def reset(self) -> None:
        self.event_queue.clear()

    def _require_query_execution(
        self,
    ) -> tuple[
        SimpleServiceQueryEngine,
        QueryResourceHolder,
        BaseUnitOfWork,
    ]:
        if (
            self.query_engine is None
            or self.query_resource_holder is None
            or self.query_uow is None
        ):
            raise RuntimeError(
                "Simple service query execution is not configured."
            )

        return (
            self.query_engine,
            self.query_resource_holder,
            self.query_uow,
        )
