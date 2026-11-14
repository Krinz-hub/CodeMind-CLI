"""Order processing domain service."""

from __future__ import annotations

from typing import List
from models import Item, Order
from storage import OrderRepository


class OrderService:
    """Coordinates pricing, validation, and persistence of orders."""

    def __init__(self, repository: OrderRepository | None = None):
        self.repository = repository or OrderRepository()

    def create_order(
        self,
        order_id: str,
        customer_id: str,
        items: List[Item],
        tax_rate: float = 0.05,
    ) -> Order:
        if not items:
            raise ValueError("Order must contain at least one item")

        order = Order(
            order_id=order_id,
            customer_id=customer_id,
            items=items,
            tax_rate=tax_rate,
        )
        return self.repository.save(order)
