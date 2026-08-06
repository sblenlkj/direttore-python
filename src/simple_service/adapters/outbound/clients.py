class RecordingStockReceiptClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def validate_receipt(self, product_id: str, quantity: int) -> None:
        self.calls.append((product_id, quantity))

