from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from direttore.core.modular_monolith_support.uow_routing_registries.base_uow_routing_registry import (
    BaseUowRoutingRegistry,
    UowRoutingRegistryItem,
)
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.event_handler_registry import (
    EventHandlerRegistry,
)


class EventUowRoutingRegistry(BaseUowRoutingRegistry):
    @classmethod
    def from_registry(
        cls,
        *,
        registry: EventHandlerRegistry,
        root_uow_type: type[BaseUnitOfWork],
    ) -> EventUowRoutingRegistry:
        routing_registry = cls()

        for registration in registry.iter_registrations():
            routing_registry.register_event_handler(
                handler_type=registration.handler_type,
                root_uow_type=root_uow_type,
            )

        return routing_registry

    @classmethod
    def from_registry_items(
        cls,
        items: Iterable[UowRoutingRegistryItem[EventHandlerRegistry]],
    ) -> EventUowRoutingRegistry:
        routing_registry = cls()

        for item in items:
            for registration in item.registry.iter_registrations():
                routing_registry.register_event_handler(
                    handler_type=registration.handler_type,
                    root_uow_type=item.root_uow_type,
                )

        return routing_registry

    def register_event_handler(
        self,
        *,
        handler_type: type[Any],
        root_uow_type: type[BaseUnitOfWork],
    ) -> None:
        self.register(
            handler_type=handler_type,
            root_uow_type=root_uow_type,
        )

    def get_uow_type_by_handler_type(
        self,
        handler_type: type[Any],
    ) -> type[BaseUnitOfWork]:
        return super().get_uow_type_by_handler_type(handler_type)