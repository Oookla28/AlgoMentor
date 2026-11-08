"""Tests for the inventory demo. These are not executed by the product task."""

import unittest

from inventory import Inventory, Item


class InventoryTest(unittest.TestCase):
    def test_take_reduces_stock(self):
        inventory = Inventory()
        inventory.add(Item('notebook', 3))
        inventory.take('notebook', 1)
        self.assertEqual(inventory.items['notebook'].stock, 2)

    def test_take_missing_item_raises(self):
        inventory = Inventory()
        with self.assertRaises(KeyError):
            inventory.take('missing', 1)

    def test_take_too_many_should_raise(self):
        inventory = Inventory()
        inventory.add(Item('notebook', 1))
        with self.assertRaises(ValueError):
            inventory.take('notebook', 5)
