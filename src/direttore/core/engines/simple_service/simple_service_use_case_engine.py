from __future__ import annotations

from collections.abc import Mapping

from direttore.core.contracts.handlers import (
    UseCaseHandler,
    UseCaseHandlerContext,
    UseCaseHandlerExecutionMode,
    UseCaseHandlerResult,
)
from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.engines.base_engine import BaseUseCaseEngine
from direttore.core.engines.engine_exceptions import (
    EngineEventLimitExceededError,
)
from direttore.core.engines.simple_service.simple_service_config import (
    SimpleServiceUseCaseEngineConfig,
)
from direttore.core.engines.simple_service.simple_service_payload_loader import (
    SimpleServiceKeyPayloadLoader,
)
from direttore.core.event_dispatchers.simple_service_event_dispatcher import (
    SimpleServiceEventDispatcher,
)
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import (
    AbstractUseCaseResourceHolder,
)
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.registrations import (
    UseCaseHandlerRegistration,
)
from direttore.core.resolvers.resolved_handlers import ResolvedHandler
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)
from direttore.core.tracing import Span, SpanFactory


type ResolvedUseCaseHandler = ResolvedHandler[
    UseCaseHandler,
    UseCaseHandlerRegistration,
]


class SimpleServiceUseCaseEngine(BaseUseCaseEngine):
    def __init__(
        self,
        *,
        resolver: UseCaseHandlerResolver,
        event_dispatcher: SimpleServiceEventDispatcher | None = None,
        span_factory: SpanFactory[object] | None = None,
        config: SimpleServiceUseCaseEngineConfig | None = None,
    ) -> None:
        self.resolver = resolver
        self.event_dispatcher = event_dispatcher
        self.span_factory = span_factory
        self.config = config or SimpleServiceUseCaseEngineConfig()

    async def handle(
        self,
        *,
        command: UseCaseCommand,
        input: object,
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        event_queue.clear()

        try:
            resolved = self.resolver.resolve(
                type(command),
            )

            return await self._handle_resolved(
                command=command,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                event_queue=event_queue,
                trace=trace,
            )
        finally:
            event_queue.clear()

    async def handle_by_key(
        self,
        *,
        key: str,
        payload: Mapping[str, object],
        input: object,
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        event_queue.clear()

        try:
            command, resolved = self._resolve_command_by_key(
                key=key,
                payload=payload,
            )

            return await self._handle_resolved(
                command=command,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                event_queue=event_queue,
                trace=trace,
            )
        finally:
            event_queue.clear()

    async def handle_operation(
        self,
        *,
        operation_id: int | str,
        input: object,
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        event_queue.clear()

        try:
            if self.span_factory is None:
                return await self._execute_operation(
                    operation_id=operation_id,
                    input=input,
                    resource_holder=resource_holder,
                    uow=uow,
                    event_queue=event_queue,
                    span=None,
                )

            async with self.span_factory.create_span(
                trace=trace,
                name=(
                    "simple.use_case.handle_operation "
                    f"{operation_id}"
                ),
                attributes={
                    "operation.id": operation_id,
                    "operation.kind": "stored_use_case",
                },
            ) as span:
                span.add_event(
                    "simple.use_case.operation.started",
                )

                result = await self._execute_operation(
                    operation_id=operation_id,
                    input=input,
                    resource_holder=resource_holder,
                    uow=uow,
                    event_queue=event_queue,
                    span=span,
                )

                span.add_event(
                    "simple.use_case.operation.finished",
                )
        finally:
            event_queue.clear()

        return result

    async def _handle_resolved(
        self,
        *,
        command: UseCaseCommand,
        input: object,
        resolved: ResolvedUseCaseHandler,
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        trace: object | None,
    ) -> UseCaseHandlerResult:
        if self.span_factory is None:
            return await self._execute(
                command=command,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                event_queue=event_queue,
                span=None,
            )

        async with self.span_factory.create_span(
            trace=trace,
            name=self._build_span_name(
                operation="simple.use_case.handle",
                message=command,
            ),
            attributes=self._build_span_attributes(
                message=command,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event(
                "simple.use_case.execution.started",
            )

            result = await self._execute(
                command=command,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                event_queue=event_queue,
                span=span,
            )

            span.add_event(
                "simple.use_case.execution.finished",
            )

        return result

    async def _execute(
        self,
        *,
        command: UseCaseCommand,
        input: object,
        resolved: ResolvedUseCaseHandler,
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        span: Span | None,
    ) -> UseCaseHandlerResult:
        execution_mode = resolved.registration.execution_mode
        self._validate_execution_mode(
            execution_mode,
        )

        async with resource_holder:
            lifecycle_context = (
                await resolved.registration.lifecycle.create_context(
                    input,
                    resolved.registration.config,
                    uow,
                )
            )

            context = UseCaseHandlerContext(
                uow=uow,
                queue=event_queue,
                lifecycle_context=lifecycle_context,
                span=span,
            )

            result = await resolved.handler.handle(
                command,
                context,
            )

            if (
                execution_mode
                == UseCaseHandlerExecutionMode.IN_TRANSACTION
            ):
                await self._drain_events(
                    event_queue=event_queue,
                    uow=uow,
                    span=span,
                )

                return result

        await self._drain_events(
            event_queue=event_queue,
            uow=uow,
            span=span,
        )

        return result

    async def _execute_operation(
        self,
        *,
        operation_id: int | str,
        input: object,
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        span: Span | None,
    ) -> UseCaseHandlerResult:
        payload_loader = self._require_payload_key_loader()

        async with resource_holder:
            key_payload_pair = (
                await payload_loader.get_key_payload_pair(
                    operation_id,
                    uow,
                )
            )

            command, resolved = self._resolve_command_by_key(
                key=key_payload_pair.key,
                payload=key_payload_pair.payload,
            )

            execution_mode = resolved.registration.execution_mode
            self._validate_execution_mode(
                execution_mode,
            )

            if span is not None:
                span.set_attribute(
                    "operation.key",
                    key_payload_pair.key,
                )

                for key, value in self._build_span_attributes(
                    message=command,
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
                    "simple.use_case.operation.loaded",
                )

            lifecycle_context = (
                await resolved.registration.lifecycle.create_context(
                    input,
                    resolved.registration.config,
                    uow,
                )
            )

            context = UseCaseHandlerContext(
                uow=uow,
                queue=event_queue,
                lifecycle_context=lifecycle_context,
                span=span,
            )

            result = await resolved.handler.handle(
                command,
                context,
            )

            if (
                execution_mode
                == UseCaseHandlerExecutionMode.IN_TRANSACTION
            ):
                await self._drain_events(
                    event_queue=event_queue,
                    uow=uow,
                    span=span,
                )

                return result

        await self._drain_events(
            event_queue=event_queue,
            uow=uow,
            span=span,
        )

        return result

    def _resolve_command_by_key(
        self,
        *,
        key: str,
        payload: Mapping[str, object],
    ) -> tuple[
        UseCaseCommand,
        ResolvedUseCaseHandler,
    ]:
        resolved = self.resolver.resolve_by_key(
            key,
        )

        command = self._build_command_from_payload(
            key=key,
            payload=payload,
            command_type=resolved.registration.command_type,
        )

        return (
            command,
            resolved,
        )

    def _require_payload_key_loader(
        self,
    ) -> SimpleServiceKeyPayloadLoader:
        if self.config.payload_key_loader is None:
            raise RuntimeError(
                "Simple service use case operation execution is not "
                "configured. handle_operation(...) requires "
                "payload_key_loader."
            )

        return self.config.payload_key_loader

    async def _drain_events(
        self,
        *,
        event_queue: EventQueue,
        uow: BaseUnitOfWork,
        span: Span | None,
    ) -> None:
        if self.event_dispatcher is None:
            return

        processed_events = 0

        while not event_queue.is_empty:
            if (
                processed_events
                >= self.config.max_processed_events
            ):
                raise EngineEventLimitExceededError(
                    "Use case event processing limit exceeded. "
                    f"Limit={self.config.max_processed_events}."
                )

            event = event_queue.pop()

            await self.event_dispatcher.dispatch(
                event=event,
                uow=uow,
                span=span,
            )

            processed_events += 1
