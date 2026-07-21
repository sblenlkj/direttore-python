from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.application.execution_slot_pool import (
    ExecutionSlotPool,
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
from direttore.core.event_dispatchers.simple_service_event_dispatcher import (
    SimpleServiceEventDispatcher,
)
from direttore.core.modules.auth import (
    Authenticator,
    ContextAuthenticator,
)
from direttore.core.tracing import Tracer
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


class SimpleServiceDirettoreApplication[
    AuthInputT,
    AuthT,
    TraceInputT,
    TraceT,
]:
    def __init__(
        self,
        *,
        config: SimpleServiceDirettoreConfig[
            AuthInputT,
            AuthT,
            TraceInputT,
            TraceT,
        ],
        container: Container,
        initial_slot_count: int = 5,
        max_slot_count: int = 20,
    ) -> None:
        self.config = config
        self.container = container

        self.event_dispatcher = self._build_event_dispatcher()
        self.use_case_engine = self._build_use_case_engine()
        self.query_engine = self._build_query_engine()

        self.slot_pool = ExecutionSlotPool[
            SimpleServiceExecutionSlot[AuthInputT, AuthT, TraceT]
        ](
            slot_factory=self._create_slot,
            initial_slot_count=initial_slot_count,
            max_slot_count=max_slot_count,
        )

    async def handle(
        self,
        command: UseCaseCommand,
        *,
        auth_input: AuthInputT | None = None,
        trace_input: TraceInputT | None = None,
    ) -> UseCaseHandlerResult:
        slot = await self.slot_pool.acquire()

        try:
            trace = self._resolve_trace(trace_input)

            return await slot.handle(
                command=command,
                authenticator=self._get_authenticator(),
                auth_input=auth_input,
                trace=trace,
                tracer=self._get_tracer(),
            )
        finally:
            await self.slot_pool.release(slot)

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        auth_input: AuthInputT | None = None,
        trace_input: TraceInputT | None = None,
    ) -> UseCaseHandlerResult:
        slot = await self.slot_pool.acquire()

        try:
            trace = self._resolve_trace(trace_input)

            return await slot.handle_by_key(
                key=key,
                payload=payload,
                authenticator=self._get_authenticator(),
                auth_input=auth_input,
                trace=trace,
                tracer=self._get_tracer(),
            )
        finally:
            await self.slot_pool.release(slot)

    async def handle_query(
        self,
        query: Query,
        *,
        auth_input: AuthInputT | None = None,
        trace_input: TraceInputT | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Simple service query execution is not configured."
            )

        slot = await self.slot_pool.acquire()

        try:
            trace = self._resolve_trace(trace_input)

            return await slot.handle_query(
                query=query,
                authenticator=self._get_authenticator(),
                auth_input=auth_input,
                trace=trace,
                tracer=self._get_tracer(),
            )
        finally:
            await self.slot_pool.release(slot)

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        auth_input: AuthInputT | None = None,
        trace_input: TraceInputT | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Simple service query execution is not configured."
            )

        slot = await self.slot_pool.acquire()

        try:
            trace = self._resolve_trace(trace_input)

            return await slot.handle_query_by_key(
                key=key,
                payload=payload,
                authenticator=self._get_authenticator(),
                auth_input=auth_input,
                trace=trace,
                tracer=self._get_tracer(),
            )
        finally:
            await self.slot_pool.release(slot)

    def validate(self) -> None:
        self.use_case_engine.resolver.validate()

        if self.query_engine is not None:
            self.query_engine.resolver.validate()

        if self.event_dispatcher is not None:
            self.event_dispatcher.validate_event_handlers()

    def slot_pool_stats(self):
        return self.slot_pool.stats()

    def _build_event_dispatcher(
        self,
    ) -> SimpleServiceEventDispatcher[TraceT] | None:
        if self.config.handlers.event_registry is None:
            return None

        event_resolver = EventHandlerResolver(
            registry=self.config.handlers.event_registry,
            container=self.container,
        )

        return SimpleServiceEventDispatcher[TraceT](
            resolver=event_resolver,
        )

    def _build_use_case_engine(
        self,
    ) -> SimpleServiceUseCaseEngine[AuthInputT, AuthT, TraceT]:
        use_case_resolver = UseCaseHandlerResolver(
            registry=self.config.handlers.use_case_registry,
            container=self.container,
        )

        return SimpleServiceUseCaseEngine[
            AuthInputT,
            AuthT,
            TraceT,
        ](
            resolver=use_case_resolver,
            event_dispatcher=self.event_dispatcher,
            authorizer=self._get_authorizer(),
            config=self.config.use_case_engine,
        )

    def _build_query_engine(
        self,
    ) -> SimpleServiceQueryEngine[AuthInputT, AuthT, TraceT] | None:
        if self.config.handlers.query_registry is None:
            return None

        query_resolver = QueryHandlerResolver(
            registry=self.config.handlers.query_registry,
            container=self.container,
        )

        return SimpleServiceQueryEngine[
            AuthInputT,
            AuthT,
            TraceT,
        ](
            resolver=query_resolver,
            authorizer=self._get_authorizer(),
        )

    def _create_slot(
        self,
    ) -> SimpleServiceExecutionSlot[AuthInputT, AuthT, TraceT]:
        return SimpleServiceExecutionSlot(
            use_case_engine=self.use_case_engine,
            query_engine=self.query_engine,
            use_case_resource_holder_factory=(
                self.config.slot.use_case_resource_holder_factory
            ),
            query_resource_holder_factory=(
                self.config.slot.query_resource_holder_factory
            ),
            use_case_uow_factory=self.config.slot.use_case_uow_factory,
            query_uow_factory=self.config.slot.query_uow_factory,
        )

    def _resolve_trace(
        self,
        trace_input: TraceInputT | None,
    ) -> TraceT | None:
        if self.config.tracing is None:
            return None

        if self.config.tracing.trace_resolver is None:
            return None

        return self.config.tracing.trace_resolver.resolve_trace(
            trace_input,
        )

    def _get_authenticator(
        self,
    ) -> (
        Authenticator[AuthInputT, AuthT]
        | ContextAuthenticator[AuthInputT, AuthT, Any]
        | None
    ):
        if self.config.auth is None:
            return None

        return self.config.auth.authenticator

    def _get_authorizer(self):
        if self.config.auth is None:
            return None

        return self.config.auth.authorizer

    def _get_tracer(self) -> Tracer[TraceT] | None:
        if self.config.tracing is None:
            return None

        return self.config.tracing.tracer