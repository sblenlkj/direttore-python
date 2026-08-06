from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Product:
    product_id: str
    name: str
    quantity: int = 0


class OrderStatus(StrEnum):
    PLACED = "placed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    product_id: str
    quantity: int
    status: OrderStatus = OrderStatus.PLACED

