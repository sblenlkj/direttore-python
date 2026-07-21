from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.application.base_execution_slot import (
    BaseExecutionSlot,
)
from direttore.application.simple_service.config import (
    QueryResourceHolderFactory,
    QueryUnitOfWorkFactory,
    UseCaseResourceHolderFactory,
    UseCaseUnitOfWorkFactory,
)
from direttore.core.contracts.handlers import (
    QueryHandlerResult,
    UseCaseHandlerResult,
)
from direttore.core.contracts.messages import (
    Query,
    UseCaseCommand,
)
from direttore.core.engines.simple_service.simple_service_query_engine import (
    SimpleServiceQueryEngine,
)
from direttore.core.engines.simple_service.simple_service_use_case_engine import (
    SimpleServiceUseCaseEngine,
)
from direttore.core.modules.auth import (
    Authenticator,
    ContextAuthenticator,
)
from direttore.core.tracing import Tracer
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import (
    AbstractUseCaseResourceHolder,
    QueryResourceHolder,
)
from direttore.core.primitives.uow import BaseUnitOfWork


class SimpleServiceExecutionSlot[
    AuthInputT,
    AuthT,
    TraceT,
](BaseExecutionSlot):
    def __init__(
        self,
        *,
        use_case_engine: SimpleServiceUseCaseEngine[
            AuthInputT,
            AuthT,
            TraceT,
        ],
        use_case_resource_holder_factory: UseCaseResourceHolderFactory,
        use_case_uow_factory: UseCaseUnitOfWorkFactory,
        query_engine: SimpleServiceQueryEngine[AuthInputT, AuthT, TraceT]
        | None = None,
        query_resource_holder_factory: QueryResourceHolderFactory | None = None,
        query_uow_factory: QueryUnitOfWorkFactory | None = None,
    ) -> None:
        self.use_case_engine = use_case_engine
        self.query_engine = query_engine

        self.use_case_resource_holder: AbstractUseCaseResourceHolder = (
            use_case_resource_holder_factory()
        )
        self.use_case_uow: BaseUnitOfWork = use_case_uow_factory(
            self.use_case_resource_holder,
        )

        self.query_resource_holder: QueryResourceHolder | None = None
        self.query_uow: BaseUnitOfWork | None = None

        if (
            query_resource_holder_factory is not None
            and query_uow_factory is not None
        ):
            self.query_resource_holder = query_resource_holder_factory()
            self.query_uow = query_uow_factory(
                self.query_resource_holder,
            )

        self.event_queue: EventQueue = EventQueue()

    async def handle(
        self,
        *,
        command: UseCaseCommand,
        authenticator: (
            Authenticator[AuthInputT, AuthT]
            | ContextAuthenticator[AuthInputT, AuthT, Any]
            | None
        ) = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> UseCaseHandlerResult:
        return await self.use_case_engine.handle(
            command=command,
            resource_holder=self.use_case_resource_holder,
            uow=self.use_case_uow,
            event_queue=self.event_queue,
            authenticator=authenticator,
            auth_input=auth_input,
            trace=trace,
            tracer=tracer,
        )

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        authenticator: (
            Authenticator[AuthInputT, AuthT]
            | ContextAuthenticator[AuthInputT, AuthT, Any]
            | None
        ) = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> UseCaseHandlerResult:
        resolved = self.use_case_engine.resolver.resolve_by_key(key)

        command = self._build_command_from_payload(
            key=key,
            payload=payload,
            command_type=resolved.registration.command_type,
        )

        return await self.handle(
            command=command,
            authenticator=authenticator,
            auth_input=auth_input,
            trace=trace,
            tracer=tracer,
        )

    async def handle_query(
        self,
        *,
        query: Query,
        authenticator: (
            Authenticator[AuthInputT, AuthT]
            | ContextAuthenticator[AuthInputT, AuthT, Any]
            | None
        ) = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Simple service query execution is not configured."
            )

        if self.query_resource_holder is None or self.query_uow is None:
            raise RuntimeError(
                "Simple service query slot resources are not configured."
            )

        return await self.query_engine.handle(
            query=query,
            resource_holder=self.query_resource_holder,
            uow=self.query_uow,
            authenticator=authenticator,
            auth_input=auth_input,
            trace=trace,
            tracer=tracer,
        )

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        authenticator: (
            Authenticator[AuthInputT, AuthT]
            | ContextAuthenticator[AuthInputT, AuthT, Any]
            | None
        ) = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Simple service query execution is not configured."
            )

        resolved = self.query_engine.resolver.resolve_by_key(key)

        query = self._build_query_from_payload(
            key=key,
            payload=payload,
            query_type=resolved.registration.query_type,
        )

        return await self.handle_query(
            query=query,
            authenticator=authenticator,
            auth_input=auth_input,
            trace=trace,
            tracer=tracer,
        )

    def reset(self) -> None:
        self.event_queue.clear()