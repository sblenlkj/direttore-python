from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.core.contracts.handlers import (
    QueryHandler,
    QueryHandlerContext,
    QueryHandlerResult,
    UseCaseHandler,
    UseCaseHandlerContext,
    UseCaseHandlerResult,
)
from direttore.core.contracts.messages import Query, UseCaseCommand
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.uow_routing_registries.query_uow_routing_registry import (
    QueryUowRoutingRegistry,
)
from direttore.core.modular_monolith_support.uow_routing_registries.use_case_uow_routing_registry import (
    UseCaseUowRoutingRegistry,
)
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.registrations import (
    QueryHandlerRegistration,
    UseCaseHandlerRegistration,
)
from direttore.core.resolvers.query_handler_resolver import (
    QueryHandlerResolver,
)
from direttore.core.resolvers.resolved_handlers import ResolvedHandler
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)
from direttore.core.tracing import Span


class ModularMonolithExecutionRuntime:
    """Slot-owned runtime for in-process bounded-context invocations.

    The runtime owns routing dependencies, dependency overrides, the event
    queue, and the lifecycle context installed by the active engine execution.

    Tracing state is never stored in the runtime. A caller may pass its current
    span to invoke(...) or invoke_query(...). The runtime then creates a child
    span representing the bounded-context invocation.
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
        dependency_overrides: Mapping[type[Any], Any] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._event_queue = event_queue

        self._use_case_resolver = use_case_resolver
        self._use_case_uow_routing = use_case_uow_routing

        self._query_resolver = query_resolver
        self._query_uow_routing = query_uow_routing

        self._dependency_overrides = dependency_overrides
        self._lifecycle_context: object | None = None

    def _get_dependency_overrides(
        self,
    ) -> Mapping[type[Any], Any] | None:
        return self._dependency_overrides

    def _set_dependency_overrides(
        self,
        dependency_overrides: Mapping[type[Any], Any] | None,
    ) -> None:
        self._dependency_overrides = dependency_overrides

    def _set_lifecycle_context(
        self,
        lifecycle_context: object | None,
    ) -> None:
        self._lifecycle_context = lifecycle_context

    async def invoke(
        self,
        command: UseCaseCommand,
        *,
        span: Span | None = None,
    ) -> UseCaseHandlerResult:
        resolved = self._use_case_resolver.resolve(
            type(command),
            overrides=self._dependency_overrides,
        )
        uow = self._get_use_case_uow(resolved)

        if span is None:
            return await self._invoke(
                command=command,
                resolved=resolved,
                uow=uow,
                span=None,
            )

        async with span.child(
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
        ) as child:
            child.add_event("runtime.invoke.started")

            result = await self._invoke(
                command=command,
                resolved=resolved,
                uow=uow,
                span=child,
            )

            child.add_event("runtime.invoke.finished")

        return result

    async def invoke_query(
        self,
        query: Query,
        *,
        span: Span | None = None,
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

        if span is None:
            return await self._invoke_query(
                query=query,
                resolved=resolved,
                uow=uow,
                span=None,
            )

        async with span.child(
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
        ) as child:
            child.add_event("runtime.invoke_query.started")

            result = await self._invoke_query(
                query=query,
                resolved=resolved,
                uow=uow,
                span=child,
            )

            child.add_event("runtime.invoke_query.finished")

        return result

    async def _invoke(
        self,
        *,
        command: UseCaseCommand,
        resolved: ResolvedHandler[
            UseCaseHandler,
            UseCaseHandlerRegistration,
        ],
        uow: BaseUnitOfWork,
        span: Span | None,
    ) -> UseCaseHandlerResult:
        context = UseCaseHandlerContext(
            uow=uow,
            queue=self._event_queue,
            lifecycle_context=self._lifecycle_context,
            span=span,
        )

        return await resolved.handler.handle(
            command,
            context,
        )

    async def _invoke_query(
        self,
        *,
        query: Query,
        resolved: ResolvedHandler[
            QueryHandler,
            QueryHandlerRegistration,
        ],
        uow: BaseUnitOfWork,
        span: Span | None,
    ) -> QueryHandlerResult:
        context = QueryHandlerContext(
            uow=uow,
            lifecycle_context=self._lifecycle_context,
            span=span,
        )

        return await resolved.handler.handle(
            query,
            context,
        )

    def _get_use_case_uow(
        self,
        resolved: ResolvedHandler[
            UseCaseHandler,
            UseCaseHandlerRegistration,
        ],
    ) -> BaseUnitOfWork:
        root_uow_type = (
            self._use_case_uow_routing.get_uow_type_by_handler_type(
                resolved.handler_type,
            )
        )

        return self._coordinator.get_use_case_uow(root_uow_type)

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
            "invocation.kind": "bounded_context",
        }
