from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.core.contracts.handlers import (
    QueryHandlerContext,
    QueryHandlerResult,
    UseCaseHandlerContext,
    UseCaseHandlerResult,
)
from direttore.core.contracts.messages import (
    Query,
    UseCaseCommand,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.uow_routing_registries.query_uow_routing_registry import (
    QueryUowRoutingRegistry,
)
from direttore.core.modular_monolith_support.uow_routing_registries.use_case_uow_routing_registry import (
    UseCaseUowRoutingRegistry,
)
from direttore.core.modules.auth import (
    ModularAuthorizationLocationKind,
    ModularAuthorizer,
)
from direttore.core.tracing import TraceSpan, Tracer
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.resolvers.query_handler_resolver import (
    QueryHandlerResolver,
)
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)


class ModularMonolithExecutionRuntime[AuthT, TraceT]:
    """Slot-owned internal execution runtime.

    The runtime is used by execution-scoped in-process clients inside handlers:

        await runtime.invoke(command)
        await runtime.invoke_query(query)

    It belongs to one execution slot and keeps slot-scope dependency overrides.
    Per request/execution it receives mutable execution state:

        auth
        trace
        parent_span

    The runtime does not create Unit of Work objects. It asks the slot-owned
    ModularUnitOfWorkCoordinator for already registered UoW instances.
    """

    def __init__(
        self,
        *,
        coordinator: ModularUnitOfWorkCoordinator,
        event_queue: EventQueue,
        use_case_resolver: UseCaseHandlerResolver,
        use_case_uow_routing: UseCaseUowRoutingRegistry,
        query_resolver: QueryHandlerResolver | None = None,
        query_uow_routing: QueryUowRoutingRegistry | None = None,
        authorizer: ModularAuthorizer[AuthT] | None = None,
        tracer: Tracer[TraceT] | None = None,
        dependency_overrides: Mapping[type[Any], Any] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._event_queue = event_queue

        self._use_case_resolver = use_case_resolver
        self._query_resolver = query_resolver

        self._use_case_uow_routing = use_case_uow_routing
        self._query_uow_routing = query_uow_routing

        self._authorizer = authorizer
        self._tracer = tracer

        self._dependency_overrides: Mapping[type[Any], Any] | None = (
            dependency_overrides
        )
        self._auth: AuthT | None = None
        self._trace: TraceT | None = None
        self._parent_span: TraceSpan | None = None

    @property
    def auth(self) -> AuthT | None:
        return self._auth

    @property
    def trace(self) -> TraceT | None:
        return self._trace

    @property
    def parent_span(self) -> TraceSpan | None:
        return self._parent_span

    @property
    def dependency_overrides(self) -> Mapping[type[Any], Any] | None:
        return self._dependency_overrides

    def set_auth(
        self,
        auth: AuthT | None,
    ) -> None:
        self._auth = auth

    def clear_auth(self) -> None:
        self._auth = None

    def set_trace(
        self,
        trace: TraceT | None,
    ) -> None:
        self._trace = trace

    def clear_trace(self) -> None:
        self._trace = None

    def set_parent_span(
        self,
        parent_span: TraceSpan | None,
    ) -> None:
        self._parent_span = parent_span

    def clear_parent_span(self) -> None:
        self._parent_span = None

    def set_dependency_overrides(
        self,
        overrides: Mapping[type[Any], Any] | None,
    ) -> None:
        self._dependency_overrides = overrides

    async def invoke(
        self,
        command: UseCaseCommand,
    ) -> UseCaseHandlerResult:
        resolved = self._use_case_resolver.resolve(
            type(command),
            overrides=self._dependency_overrides,
        )

        root_uow_type = self._use_case_uow_routing.get_uow_type_by_handler_type(
            resolved.handler_type,
        )
        uow = self._coordinator.get_use_case_uow(root_uow_type)

        if self._tracer is None:
            return await self._invoke_without_span(
                command=command,
                resolved=resolved,
                uow=uow,
            )

        async with self._tracer.start_span(
            trace=self._trace,
            name=self._build_span_name(
                operation="runtime.invoke",
                message=command,
                source_name=resolved.registration.source_name,
            ),
            attributes=self._build_span_attributes(
                message=command,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
                message_kind="use_case_command",
            ),
            parent_span=self._parent_span,
        ) as span:
            span.add_event("runtime.invoke.started")

            previous_parent_span = self._parent_span
            self._parent_span = span

            try:
                result = await self._invoke_without_span(
                    command=command,
                    resolved=resolved,
                    uow=uow,
                )
            finally:
                self._parent_span = previous_parent_span

            span.add_event("runtime.invoke.finished")

        return result

    async def invoke_query(
        self,
        query: Query,
    ) -> QueryHandlerResult:
        query_resolver = self._require_query_resolver()
        query_uow_routing = self._require_query_uow_routing()

        resolved = query_resolver.resolve(
            type(query),
            overrides=self._dependency_overrides,
        )

        root_uow_type = query_uow_routing.get_uow_type_by_handler_type(
            resolved.handler_type,
        )
        uow = self._coordinator.get_query_uow(root_uow_type)

        if self._tracer is None:
            return await self._invoke_query_without_span(
                query=query,
                resolved=resolved,
                uow=uow,
            )

        async with self._tracer.start_span(
            trace=self._trace,
            name=self._build_span_name(
                operation="runtime.invoke_query",
                message=query,
                source_name=resolved.registration.source_name,
            ),
            attributes=self._build_span_attributes(
                message=query,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
                message_kind="query",
            ),
            parent_span=self._parent_span,
        ) as span:
            span.add_event("runtime.invoke_query.started")

            previous_parent_span = self._parent_span
            self._parent_span = span

            try:
                result = await self._invoke_query_without_span(
                    query=query,
                    resolved=resolved,
                    uow=uow,
                )
            finally:
                self._parent_span = previous_parent_span

            span.add_event("runtime.invoke_query.finished")

        return result

    async def _invoke_without_span(
        self,
        *,
        command: UseCaseCommand,
        resolved: Any,
        uow: Any,
    ) -> UseCaseHandlerResult:
        self._authorize(
            allowed_access_tags=resolved.registration.config.allowed_access_tags,
        )

        context = UseCaseHandlerContext(
            uow=uow,
            queue=self._event_queue,
            auth=self._auth,
            tracer=self._trace,
        )

        return await resolved.handler(
            command,
            context,
        )

    async def _invoke_query_without_span(
        self,
        *,
        query: Query,
        resolved: Any,
        uow: Any,
    ) -> QueryHandlerResult:
        self._authorize(
            allowed_access_tags=resolved.registration.config.allowed_access_tags,
        )

        context = QueryHandlerContext(
            uow=uow,
            auth=self._auth,
            tracer=self._trace,
        )

        return await resolved.handler(
            query,
            context,
        )

    def _authorize(
        self,
        *,
        allowed_access_tags: frozenset[str] | None,
    ) -> None:
        if self._authorizer is None:
            return

        self._authorizer.authorize(
            allowed_access_tags=allowed_access_tags,
            auth=self._auth,
            location_kind=ModularAuthorizationLocationKind.SYSTEM_INVOKE,
        )

    def _require_query_resolver(self) -> QueryHandlerResolver:
        if self._query_resolver is None:
            raise RuntimeError(
                "Modular query execution is not configured. "
                "runtime.invoke_query(...) requires query resolver."
            )

        return self._query_resolver

    def _require_query_uow_routing(self) -> QueryUowRoutingRegistry:
        if self._query_uow_routing is None:
            raise RuntimeError(
                "Modular query UoW routing is not configured. "
                "runtime.invoke_query(...) requires query UoW routing registry."
            )

        return self._query_uow_routing

    def _build_span_name(
        self,
        *,
        operation: str,
        message: UseCaseCommand | Query,
        source_name: str | None,
    ) -> str:
        message_name = (
            f"{type(message).__module__}.{type(message).__qualname__}"
        )

        if source_name is None:
            return f"{operation} {message_name}"

        return f"{operation} {source_name}.{message_name}"

    def _build_span_attributes(
        self,
        *,
        message: UseCaseCommand | Query,
        handler_type: type[Any],
        source_name: str | None,
        key: str | None,
        message_kind: str,
    ) -> dict[str, Any]:
        return {
            "message.kind": message_kind,
            "message.type": (
                f"{type(message).__module__}.{type(message).__qualname__}"
            ),
            "handler.type": (
                f"{handler_type.__module__}.{handler_type.__qualname__}"
            ),
            "handler.source_name": source_name,
            "handler.key": key,
            "invocation.kind": "system_invoke",
        }