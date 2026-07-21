from __future__ import annotations

from typing import Any

from direttore.core.contracts.handlers import (
    QueryHandlerContext,
    QueryHandlerResult,
)
from direttore.core.contracts.messages import Query
from direttore.core.engines.config import QueryEngineConfig
from direttore.core.engines.simple_service.base_simple_service_engine import (
    BaseSimpleServiceEngine,
)
from direttore.core.modules.auth import (
    Authenticator,
    Authorizer,
    ContextAuthenticator,
)
from direttore.core.tracing import Tracer
from direttore.core.primitives.resource_holder import (
    QueryResourceHolder,
)
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.resolvers.query_handler_resolver import (
    QueryHandlerResolver,
)


class SimpleServiceQueryEngine[AuthInputT, AuthT, TraceT](
    BaseSimpleServiceEngine[AuthInputT, AuthT],
):
    def __init__(
        self,
        *,
        resolver: QueryHandlerResolver,
        authorizer: Authorizer[AuthT] | None = None,
        config: QueryEngineConfig | None = None,
    ) -> None:
        super().__init__(
            authorizer=authorizer,
        )
        self.resolver = resolver
        self.config = config or QueryEngineConfig()

    async def handle(
        self,
        *,
        query: Query,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        authenticator: (
            Authenticator[AuthInputT, AuthT]
            | ContextAuthenticator[AuthInputT, AuthT, Any]
            | None
        ) = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> QueryHandlerResult:
        resolved = self.resolver.resolve(type(query))
        handler_config = resolved.registration.config

        if isinstance(authenticator, ContextAuthenticator):
            return await self._handle_with_context_authentication(
                query=query,
                resource_holder=resource_holder,
                uow=uow,
                authenticator=authenticator,
                auth_input=auth_input,
                allowed_access_tags=handler_config.allowed_access_tags,
                trace=trace,
                tracer=tracer,
            )

        auth = await self._authenticate_without_context(
            authenticator=authenticator,
            auth_input=auth_input,
        )

        self._authorize(
            allowed_access_tags=handler_config.allowed_access_tags,
            auth=auth,
        )

        return await self._handle_with_resolved_auth(
            query=query,
            resource_holder=resource_holder,
            uow=uow,
            auth=auth,
            trace=trace,
            tracer=tracer,
        )

    async def _handle_with_context_authentication(
        self,
        *,
        query: Query,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        authenticator: ContextAuthenticator[AuthInputT, AuthT, Any],
        auth_input: AuthInputT | None,
        allowed_access_tags: frozenset[str] | None,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
    ) -> QueryHandlerResult:
        if tracer is None:
            return await self._execute_with_context_authentication(
                query=query,
                resource_holder=resource_holder,
                uow=uow,
                authenticator=authenticator,
                auth_input=auth_input,
                allowed_access_tags=allowed_access_tags,
                trace=trace,
            )

        resolved = self.resolver.resolve(type(query))

        async with tracer.start_span(
            trace=trace,
            name=self._build_span_name(
                operation="query.handle",
                message=query,
            ),
            attributes=self._build_span_attributes(
                message=query,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event("query.execution.started")

            result = await self._execute_with_context_authentication(
                query=query,
                resource_holder=resource_holder,
                uow=uow,
                authenticator=authenticator,
                auth_input=auth_input,
                allowed_access_tags=allowed_access_tags,
                trace=trace,
            )

            span.add_event("query.execution.finished")

        return result

    async def _handle_with_resolved_auth(
        self,
        *,
        query: Query,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        auth: AuthT | None,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
    ) -> QueryHandlerResult:
        if tracer is None:
            return await self._execute_with_resolved_auth(
                query=query,
                resource_holder=resource_holder,
                uow=uow,
                auth=auth,
                trace=trace,
            )

        resolved = self.resolver.resolve(type(query))

        async with tracer.start_span(
            trace=trace,
            name=self._build_span_name(
                operation="query.handle",
                message=query,
            ),
            attributes=self._build_span_attributes(
                message=query,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event("query.execution.started")

            result = await self._execute_with_resolved_auth(
                query=query,
                resource_holder=resource_holder,
                uow=uow,
                auth=auth,
                trace=trace,
            )

            span.add_event("query.execution.finished")

        return result

    async def _execute_with_context_authentication(
        self,
        *,
        query: Query,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        authenticator: ContextAuthenticator[AuthInputT, AuthT, Any],
        auth_input: AuthInputT | None,
        allowed_access_tags: frozenset[str] | None,
        trace: TraceT | None,
    ) -> QueryHandlerResult:
        async with resource_holder:
            auth = await self._authenticate_with_context(
                authenticator=authenticator,
                auth_input=auth_input,
                uow=uow,
            )

            self._authorize(
                allowed_access_tags=allowed_access_tags,
                auth=auth,
            )

            result = await self._call_handler(
                query=query,
                uow=uow,
                auth=auth,
                trace=trace,
            )

        return result

    async def _execute_with_resolved_auth(
        self,
        *,
        query: Query,
        resource_holder: QueryResourceHolder,
        uow: BaseUnitOfWork,
        auth: AuthT | None,
        trace: TraceT | None,
    ) -> QueryHandlerResult:
        async with resource_holder:
            result = await self._call_handler(
                query=query,
                uow=uow,
                auth=auth,
                trace=trace,
            )

        return result

    async def _call_handler(
        self,
        *,
        query: Query,
        uow: BaseUnitOfWork,
        auth: AuthT | None,
        trace: TraceT | None,
    ) -> QueryHandlerResult:
        resolved = self.resolver.resolve(type(query))

        context = QueryHandlerContext(
            uow=uow,
            auth=auth,
            tracer=trace,
        )

        return await resolved.handler(
            query,
            context,
        )