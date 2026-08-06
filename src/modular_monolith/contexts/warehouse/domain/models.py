from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Product:
    product_id: str
    name: str
    quantity: int = 0

