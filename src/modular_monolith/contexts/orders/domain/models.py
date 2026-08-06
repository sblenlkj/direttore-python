from dataclasses import dataclass
from enum import StrEnum


class OrderStatus(StrEnum):
    PLACED = "placed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    product_id: str
    quantity: int
    status: OrderStatus = OrderStatus.PLACED

