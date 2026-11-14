"""Data models for Order Processing Service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Item:
    sku: str
    name: str
    unit_price: float
    quantity: int = 1

    @property
    def total_price(self) -> float:
        return self.unit_price * self.quantity


@dataclass
class Order:
    order_id: str
    customer_id: str
    items: List[Item] = field(default_factory=list)
    tax_rate: float = 0.05
    discount_amount: float = 0.0
    status: str = "pending"

    @property
    def subtotal(self) -> float:
        return sum(item.total_price for item in self.items)

    @property
    def total(self) -> float:
        discounted = max(0.0, self.subtotal - self.discount_amount)
        tax = discounted * self.tax_rate
        return round(discounted + tax, 2)
