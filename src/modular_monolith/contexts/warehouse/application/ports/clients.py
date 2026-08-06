from typing import Protocol


class StockReceiptClient(Protocol):
    async def validate_receipt(self, product_id: str, quantity: int) -> None: ...

