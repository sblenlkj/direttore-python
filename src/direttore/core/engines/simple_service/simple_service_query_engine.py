from __future__ import annotations

from collections.abc import Mapping

from direttore.core.contracts.handlers import (
    QueryHandler,
    QueryHandlerContext,
    QueryHandlerResult,
)
from direttore.core.contracts.messages import Query
from direttore.core.engines.base_engine import BaseQueryEngine
from direttore.core.engines.simple_service.simple_service_config import (
    SimpleServiceQueryEngineConfig,
)
from direttore.core.engines.simple_service.simple_service_payload_loader import (
    SimpleServiceKeyPayloadLoader,
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


class SimpleServiceQueryEngine(BaseQueryEngine):
    def __init__(
        self,
        *,
        resolver: QueryHandlerResolver,
        span_factory: SpanFactory[object] | None = None,
        config: SimpleServiceQueryEngineConfig | None = None,
    ) -> None:
        self.resolver = resolver
        self.span_factory = span_factory
        self.config = config or SimpleServiceQueryEngineConfig()

    async def handle(
        self,
        *,
        query: Query,
        input: object,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        resolved = self.resolver.resolve(
            type(query),
        )

        return await self._handle_resolved(
            query=query,
            input=input,
            resolved=resolved,
            resource_holder=resource_holder,
            uow=uow,
            trace=trace,
        )

    async def handle_by_key(
        self,
        *,
        key: str,
        payload: Mapping[str, object],
        input: object,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        query, resolved = self._resolve_query_by_key(
            key=key,
            payload=payload,
        )

        return await self._handle_resolved(
            query=query,
            input=input,
            resolved=resolved,
            resource_holder=resource_holder,
            uow=uow,
            trace=trace,
        )

    async def handle_operation(
        self,
        *,
        operation_id: int | str,
        input: object,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        if self.span_factory is None:
            return await self._execute_operation(
                operation_id=operation_id,
                input=input,
                resource_holder=resource_holder,
                uow=uow,
                span=None,
            )

        async with self.span_factory.create_span(
            trace=trace,
            name=(
                "simple.query.handle_operation "
                f"{operation_id}"
            ),
            attributes={
                "operation.id": operation_id,
                "operation.kind": "stored_query",
            },
        ) as span:
            span.add_event(
                "simple.query.operation.started",
            )

            result = await self._execute_operation(
                operation_id=operation_id,
                input=input,
                resource_holder=resource_holder,
                uow=uow,
                span=span,
            )

            span.add_event(
                "simple.query.operation.finished",
            )

        return result

    async def _handle_resolved(
        self,
        *,
        query: Query,
        input: object,
        resolved: ResolvedQueryHandler,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        trace: object | None,
    ) -> QueryHandlerResult:
        if self.span_factory is None:
            return await self._execute(
                query=query,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                span=None,
            )

        async with self.span_factory.create_span(
            trace=trace,
            name=self._build_span_name(
                operation="simple.query.handle",
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
                "simple.query.execution.started",
            )

            result = await self._execute(
                query=query,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                span=span,
            )

            span.add_event(
                "simple.query.execution.finished",
            )

        return result

    async def _execute(
        self,
        *,
        query: Query,
        input: object,
        resolved: ResolvedQueryHandler,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        span: Span | None,
    ) -> QueryHandlerResult:
        async with resource_holder:
            lifecycle_context = (
                await resolved.registration.lifecycle.create_context(
                    input,
                    resolved.registration.config,
                    uow,
                )
            )

            context = QueryHandlerContext(
                uow=uow,
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
        uow: BaseUnitOfWork,
        span: Span | None,
    ) -> QueryHandlerResult:
        payload_loader = self._require_payload_key_loader()

        async with resource_holder:
            key_payload_pair = (
                await payload_loader.get_key_payload_pair(
                    operation_id,
                    uow,
                )
            )

            query, resolved = self._resolve_query_by_key(
                key=key_payload_pair.key,
                payload=key_payload_pair.payload,
            )

            if span is not None:
                span.set_attribute(
                    "operation.key",
                    key_payload_pair.key,
                )

                for key, value in self._build_span_attributes(
                    message=query,
                    handler_type=resolved.handler_type,
                    source_name=(
                        resolved.registration.source_name
                    ),
                    key=resolved.registration.key,
                ).items():
                    span.set_attribute(
                        key,
                        value,
                    )

                span.add_event(
                    "simple.query.operation.loaded",
                )

            lifecycle_context = (
                await resolved.registration.lifecycle.create_context(
                    input,
                    resolved.registration.config,
                    uow,
                )
            )

            context = QueryHandlerContext(
                uow=uow,
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
        payload: Mapping[str, object],
    ) -> tuple[
        Query,
        ResolvedQueryHandler,
    ]:
        resolved = self.resolver.resolve_by_key(
            key,
        )

        query = self._build_query_from_payload(
            key=key,
            payload=payload,
            query_type=resolved.registration.query_type,
        )

        return (
            query,
            resolved,
        )

    def _require_payload_key_loader(
        self,
    ) -> SimpleServiceKeyPayloadLoader:
        if self.config.payload_key_loader is None:
            raise RuntimeError(
                "Simple service query operation execution is not "
                "configured. handle_operation(...) requires "
                "payload_key_loader."
            )

        return self.config.payload_key_loader
