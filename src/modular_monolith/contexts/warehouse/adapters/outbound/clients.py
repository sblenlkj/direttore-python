from dataclasses import dataclass, field


@dataclass(slots=True)
class RecordingStockReceiptClient:
    calls: list[tuple[str, int]] = field(default_factory=list)

    async def validate_receipt(self, product_id: str, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.calls.append((product_id, quantity))

