from direttore import ModularMonolithExecutionDependencyRegistry
from modular_monolith.contexts.orders.adapters.in_process_warehouse_context_client import (
    InProcessWarehouseContextClient,
)
from modular_monolith.contexts.orders.application.ports.warehouse_context_client import (
    WarehouseContextClient,
)


def build_execution_dependencies() -> ModularMonolithExecutionDependencyRegistry:
    registry = ModularMonolithExecutionDependencyRegistry()
    registry.register(
        dependency_type=WarehouseContextClient,
        factory=lambda context: InProcessWarehouseContextClient(context.runtime),
    )
    return registry
