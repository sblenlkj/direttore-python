from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
from direttore.core.engines.modular_monolith.modular_monolith_config import (
    ModularMonolithUseCaseEngineConfig,
)
from direttore.core.engines.modular_monolith.modular_monolith_payload_loader import (
    ModularKeyPayloadLoader,
)
from direttore.core.event_dispatchers.modular_monolith_event_dispatcher import (
    ModularMonolithEventDispatcher,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.modular_monolith_support.uow_routing_registries.use_case_uow_routing_registry import (
    UseCaseUowRoutingRegistry,
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


class ModularMonolithUseCaseEngine(BaseUseCaseEngine):
    def __init__(
        self,
        *,
        resolver: UseCaseHandlerResolver,
        use_case_uow_routing: UseCaseUowRoutingRegistry,
        event_dispatcher: ModularMonolithEventDispatcher | None = None,
        span_factory: SpanFactory[object] | None = None,
        config: ModularMonolithUseCaseEngineConfig | None = None,
    ) -> None:
        self.resolver = resolver
        self.use_case_uow_routing = use_case_uow_routing
        self.event_dispatcher = event_dispatcher
        self.span_factory = span_factory
        self.config = config or ModularMonolithUseCaseEngineConfig()

    async def handle(
        self,
        *,
        command: UseCaseCommand,
        input: object,
        resource_holder: AbstractUseCaseResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        self._prepare_execution(
            runtime=runtime,
            event_queue=event_queue,
        )

        try:
            resolved = self.resolver.resolve(
                type(command),
                overrides=runtime._get_dependency_overrides(),
            )

            return await self._handle_resolved(
                command=command,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                event_queue=event_queue,
                trace=trace,
            )
        finally:
            self._finish_execution(
                runtime=runtime,
                event_queue=event_queue,
            )

    async def handle_by_key(
        self,
        *,
        key: str,
        payload: Mapping[str, Any],
        input: object,
        resource_holder: AbstractUseCaseResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        self._prepare_execution(
            runtime=runtime,
            event_queue=event_queue,
        )

        try:
            command, resolved = self._resolve_command_by_key(
                key=key,
                payload=payload,
                runtime=runtime,
            )

            return await self._handle_resolved(
                command=command,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                event_queue=event_queue,
                trace=trace,
            )
        finally:
            self._finish_execution(
                runtime=runtime,
                event_queue=event_queue,
            )

    async def handle_operation(
        self,
        *,
        operation_id: int | str,
        input: object,
        resource_holder: AbstractUseCaseResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        self._prepare_execution(
            runtime=runtime,
            event_queue=event_queue,
        )

        try:
            if self.span_factory is None:
                return await self._execute_operation(
                    operation_id=operation_id,
                    input=input,
                    resource_holder=resource_holder,
                    coordinator=coordinator,
                    runtime=runtime,
                    event_queue=event_queue,
                    span=None,
                )

            async with self.span_factory.create_span(
                trace=trace,
                name=(
                    "modular.use_case.handle_operation "
                    f"{operation_id}"
                ),
                attributes={
                    "operation.id": operation_id,
                    "operation.kind": "stored_use_case",
                },
            ) as span:
                span.add_event(
                    "modular.use_case.operation.started"
                )

                result = await self._execute_operation(
                    operation_id=operation_id,
                    input=input,
                    resource_holder=resource_holder,
                    coordinator=coordinator,
                    runtime=runtime,
                    event_queue=event_queue,
                    span=span,
                )

                span.add_event(
                    "modular.use_case.operation.finished"
                )
        finally:
            self._finish_execution(
                runtime=runtime,
                event_queue=event_queue,
            )
        return result

    async def _handle_resolved(
        self,
        *,
        command: UseCaseCommand,
        input: object,
        resolved: ResolvedUseCaseHandler,
        resource_holder: AbstractUseCaseResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
        trace: object | None,
    ) -> UseCaseHandlerResult:
        if self.span_factory is None:
            return await self._execute(
                command=command,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                event_queue=event_queue,
                span=None,
            )

        async with self.span_factory.create_span(
            trace=trace,
            name=self._build_span_name(
                operation="modular.use_case.handle",
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
                "modular.use_case.execution.started"
            )

            result = await self._execute(
                command=command,
                input=input,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                event_queue=event_queue,
                span=span,
            )

            span.add_event(
                "modular.use_case.execution.finished"
            )

        return result

    async def _execute(
        self,
        *,
        command: UseCaseCommand,
        input: object,
        resolved: ResolvedUseCaseHandler,
        resource_holder: AbstractUseCaseResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
        span: Span | None,
    ) -> UseCaseHandlerResult:
        execution_mode = resolved.registration.execution_mode
        self._validate_execution_mode(execution_mode)

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

            context = UseCaseHandlerContext(
                uow=root_uow,
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
                    coordinator=coordinator,
                    runtime=runtime,
                    span=span,
                )

                return result

        await self._drain_events(
            event_queue=event_queue,
            coordinator=coordinator,
            runtime=runtime,
            span=span,
        )

        return result

    async def _execute_operation(
        self,
        *,
        operation_id: int | str,
        input: object,
        resource_holder: AbstractUseCaseResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
        span: Span | None,
    ) -> UseCaseHandlerResult:
        payload_loader = self._require_payload_key_loader()

        async with resource_holder:
            key_payload_pair = (
                await payload_loader.get_key_payload_pair(
                    operation_id,
                    coordinator,
                )
            )

            command, resolved = self._resolve_command_by_key(
                key=key_payload_pair.key,
                payload=key_payload_pair.payload,
                runtime=runtime,
            )

            execution_mode = resolved.registration.execution_mode
            self._validate_execution_mode(execution_mode)

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

            context = UseCaseHandlerContext(
                uow=root_uow,
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
                    coordinator=coordinator,
                    runtime=runtime,
                    span=span,
                )

                return result

        await self._drain_events(
            event_queue=event_queue,
            coordinator=coordinator,
            runtime=runtime,
            span=span,
        )

        return result

    def _resolve_command_by_key(
        self,
        *,
        key: str,
        payload: Mapping[str, Any],
        runtime: ModularMonolithExecutionRuntime,
    ) -> tuple[UseCaseCommand, ResolvedUseCaseHandler]:
        resolved = self.resolver.resolve_by_key(
            key,
            overrides=runtime._get_dependency_overrides(),
        )

        command = self._build_command_from_payload(
            key=key,
            payload=payload,
            command_type=resolved.registration.command_type,
        )

        return command, resolved

    def _require_payload_key_loader(
        self,
    ) -> ModularKeyPayloadLoader:
        if self.config.payload_key_loader is None:
            raise RuntimeError(
                "Modular monolith operation execution is not "
                "configured. handle_operation(...) requires "
                "payload_key_loader."
            )

        return self.config.payload_key_loader

    async def _drain_events(
        self,
        *,
        event_queue: EventQueue,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
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
                    "Modular use case event processing limit "
                    "exceeded. "
                    f"Limit={self.config.max_processed_events}."
                )

            event = event_queue.pop()

            await self.event_dispatcher.dispatch(
                event=event,
                coordinator=coordinator,
                overrides=runtime._get_dependency_overrides(),
                span=span,
            )

            processed_events += 1

    def _get_root_uow(
        self,
        *,
        resolved: ResolvedUseCaseHandler,
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> BaseUnitOfWork:
        root_uow_type = (
            self.use_case_uow_routing
            .get_uow_type_by_handler_type(
                resolved.handler_type,
            )
        )

        return coordinator.get_use_case_uow(
            root_uow_type,
        )

    @staticmethod
    def _prepare_execution(
        *,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
    ) -> None:
        runtime._set_lifecycle_context(None)
        event_queue.clear()

    @staticmethod
    def _finish_execution(
        *,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
    ) -> None:
        runtime._set_lifecycle_context(None)
        event_queue.clear()
