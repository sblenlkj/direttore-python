from direttore import Container
from modular_monolith.contexts.warehouse.adapters.outbound.clients import (
    RecordingStockReceiptClient,
)
from modular_monolith.contexts.warehouse.application.ports.clients import (
    StockReceiptClient,
)


def build_container(client: RecordingStockReceiptClient) -> Container:
    return Container.from_mapping({StockReceiptClient: client})

