"""Order storage repository."""

from __future__ import annotations

from typing import Dict, Optional
from models import Order


class OrderRepository:
    """In-memory order store."""

    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}

    def save(self, order: Order) -> Order:
        self._orders[order.order_id] = order
        return order

    def find_by_id(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def count(self) -> int:
        return len(self._orders)
