from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.core.contracts.handlers import (
    QueryHandler,
    QueryHandlerContext,
    QueryHandlerResult,
)
from direttore.core.contracts.messages import Query
from direttore.core.engines.base_engine import BaseQueryEngine
from direttore.core.engines.modular_monolith.modular_monolith_config import (
    ModularMonolithQueryEngineConfig,
)
from direttore.core.engines.modular_monolith.modular_monolith_payload_loader import (
    ModularKeyPayloadLoader,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.modular_monolith_support.uow_routing_registries.query_uow_routing_registry import (
    QueryUowRoutingRegistry,
)
from direttore.core.primitives.resource_holder import QueryResourceHolder
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.registrations import (
    QueryHandlerRegistration,
)
from direttore.core.resolvers.query_handler_resolver import (
    QueryHandlerResolver,
)
from direttore.core.resolvers.resolved_handlers import ResolvedHandler
from direttore.core.tracing import Span, SpanFactory


type ResolvedQueryHandler = ResolvedHandler[
    QueryHandler,
    QueryHandlerRegistration,
]


class ModularMonolithQueryEngine(BaseQueryEngine):
    def __init__(
        self,
        *,
        resolver: QueryHandlerResolver,
        query_uow_routing: QueryUowRoutingRegistry,
        span_factory: SpanFactory[object] | None = None,
        config: ModularMonolithQueryEngineConfig | None = None,
    ) -> None:
        self.resolver = resolver
        self.query_uow_routing = query_uow_routing
        self.span_factory = span_factory
        self.config = config or ModularMonolithQueryEngineConfig()

    async def handle(
        self,
        *,
        query: Query,
        input: object,
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        self._prepare_execution(runtime)

        try:
            resolved = self.resolver.resolve(
                type(query),
                overrides=runtime._get_dependency_overrides(),
            )

            return await self._handle_resolved(
                query=query,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                trace=trace,
            )
        finally:
            self._finish_execution(runtime)

    async def handle_by_key(
        self,
        *,
        key: str,
        payload: Mapping[str, Any],
        input: object,
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        self._prepare_execution(runtime)

        try:
            query, resolved = self._resolve_query_by_key(
                key=key,
                payload=payload,
                runtime=runtime,
            )

            return await self._handle_resolved(
                query=query,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                trace=trace,
            )
        finally:
            self._finish_execution(runtime)

    async def handle_operation(
        self,
        *,
        operation_id: int | str,
        input: object,
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        self._prepare_execution(runtime)

        try:
            if self.span_factory is None:
                return await self._execute_operation(
                    operation_id=operation_id,
                    input=input,
                    resource_holder=resource_holder,
                    coordinator=coordinator,
                    runtime=runtime,
                    span=None,
                )

            async with self.span_factory.create_span(
                trace=trace,
                name=(
                    "modular.query.handle_operation "
                    f"{operation_id}"
                ),
                attributes={
                    "operation.id": operation_id,
                    "operation.kind": "stored_query",
                },
            ) as span:
                span.add_event(
                    "modular.query.operation.started"
                )

                result = await self._execute_operation(
                    operation_id=operation_id,
                    input=input,
                    resource_holder=resource_holder,
                    coordinator=coordinator,
                    runtime=runtime,
                    span=span,
                )

                span.add_event(
                    "modular.query.operation.finished"
                )
        finally:
            self._finish_execution(runtime)

        return result

    async def _handle_resolved(
        self,
        *,
        query: Query,
        input: object,
        resolved: ResolvedQueryHandler,
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        trace: object | None,
    ) -> QueryHandlerResult:
        if self.span_factory is None:
            return await self._execute(
                query=query,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                span=None,
            )

        async with self.span_factory.create_span(
            trace=trace,
            name=self._build_span_name(
                operation="modular.query.handle",
                message=query,
            ),
            attributes=self._build_span_attributes(
                message=query,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event(
                "modular.query.execution.started"
            )

            result = await self._execute(
                query=query,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                span=span,
            )

            span.add_event(
                "modular.query.execution.finished"
            )

        return result

    async def _execute(
        self,
        *,
        query: Query,
        input: object,
        resolved: ResolvedQueryHandler,
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        span: Span | None,
    ) -> QueryHandlerResult:
        root_uow = self._get_root_uow(
            resolved=resolved,
            coordinator=coordinator,
        )

        async with resource_holder:
            lifecycle_context = (
                await resolved.registration.lifecycle.create_context(
                    input,
                    resolved.registration.config,
                    coordinator,
                )
            )

            runtime._set_lifecycle_context(
                lifecycle_context,
            )

            context = QueryHandlerContext(
                uow=root_uow,
                lifecycle_context=lifecycle_context,
                span=span,
            )

            result = await resolved.handler.handle(
                query,
                context,
            )
        return result

    async def _execute_operation(
        self,
        *,
        operation_id: int | str,
        input: object,
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        span: Span | None,
    ) -> QueryHandlerResult:
        payload_loader = self._require_payload_key_loader()

        async with resource_holder:
            key_payload_pair = (
                await payload_loader.get_key_payload_pair(
                    operation_id,
                    coordinator,
                )
            )

            query, resolved = self._resolve_query_by_key(
                key=key_payload_pair.key,
                payload=key_payload_pair.payload,
                runtime=runtime,
            )

            root_uow = self._get_root_uow(
                resolved=resolved,
                coordinator=coordinator,
            )

            if span is not None:
                span.set_attribute(
                    "operation.key",
                    key_payload_pair.key,
                )

                span.add_event(
                    "modular.use_case.operation.loaded"
                )

            lifecycle_context = (
                await resolved.registration.lifecycle.create_context(
                    input,
                    resolved.registration.config,
                    coordinator,
                )
            )

            runtime._set_lifecycle_context(
                lifecycle_context,
            )

            context = QueryHandlerContext(
                uow=root_uow,
                lifecycle_context=lifecycle_context,
                span=span,
            )

            result = await resolved.handler.handle(
                query,
                context,
            )
        return result

    def _resolve_query_by_key(
        self,
        *,
        key: str,
        payload: Mapping[str, Any],
        runtime: ModularMonolithExecutionRuntime,
    ) -> tuple[Query, ResolvedQueryHandler]:
        resolved = self.resolver.resolve_by_key(
            key,
            overrides=runtime._get_dependency_overrides(),
        )

        query = self._build_query_from_payload(
            key=key,
            payload=payload,
            query_type=resolved.registration.query_type,
        )

        return query, resolved

    def _require_payload_key_loader(
        self,
    ) -> ModularKeyPayloadLoader:
        if self.config.payload_key_loader is None:
            raise RuntimeError(
                "Modular monolith query operation execution is not "
                "configured. handle_operation(...) requires "
                "payload_key_loader."
            )

        return self.config.payload_key_loader

    def _get_root_uow(
        self,
        *,
        resolved: ResolvedQueryHandler,
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> BaseUnitOfWork:
        root_uow_type = (
            self.query_uow_routing
            .get_uow_type_by_handler_type(
                resolved.handler_type,
            )
        )

        return coordinator.get_query_uow(
            root_uow_type,
        )

    @staticmethod
    def _prepare_execution(
        runtime: ModularMonolithExecutionRuntime,
    ) -> None:
        runtime._set_lifecycle_context(None)

    @staticmethod
    def _finish_execution(
        runtime: ModularMonolithExecutionRuntime,
    ) -> None:
        runtime._set_lifecycle_context(None)
