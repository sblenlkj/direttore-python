from direttore import Container
from modular_monolith.contexts.orders.container import (
    build_container as build_orders_container,
)
from modular_monolith.contexts.warehouse.adapters.outbound.clients import (
    RecordingStockReceiptClient,
)
from modular_monolith.contexts.warehouse.container import (
    build_container as build_warehouse_container,
)


def build_container(client: RecordingStockReceiptClient) -> Container:
    return Container.merge_many(
        [
            build_warehouse_container(client),
            build_orders_container(),
        ]
    )
