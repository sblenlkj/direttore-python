from direttore import Container
from simple_service.adapters.outbound.clients import RecordingStockReceiptClient
from simple_service.application.ports.clients import StockReceiptClient


def build_container(client: RecordingStockReceiptClient) -> Container:
    return Container.from_mapping({StockReceiptClient: client})

