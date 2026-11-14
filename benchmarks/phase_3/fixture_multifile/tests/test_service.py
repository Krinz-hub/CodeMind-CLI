"""Unit tests for OrderService."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest
from models import Item
from service import OrderService
from storage import OrderRepository


class TestOrderService(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = OrderRepository()
        self.service = OrderService(self.repo)

    def test_order_creation_and_pricing(self) -> None:
        items = [
            Item(sku="SKU-1", name="Wireless Mouse", unit_price=20.0, quantity=2),
            Item(sku="SKU-2", name="USB Cable", unit_price=10.0, quantity=1),
        ]
        # Subtotal: 20*2 + 10 = 50.0. Tax (5%): 2.50. Total: 52.50
        order = self.service.create_order("ORD-101", "CUST-1", items, tax_rate=0.05)
        self.assertEqual(order.subtotal, 50.0)
        self.assertEqual(order.total, 52.50)

        saved = self.repo.find_by_id("ORD-101")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.customer_id, "CUST-1")


if __name__ == "__main__":
    unittest.main()
