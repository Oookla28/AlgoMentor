"""A small inventory example used by the code-investigation demo."""

from dataclasses import dataclass, field


@dataclass
class Item:
    name: str
    stock: int = 0
    tags: list = field(default_factory=list)


class Inventory:
    def __init__(self):
        self.items = {}

    def add(self, item):
        self.items[item.name] = item

    def take(self, name, count):
        item = self.items.get(name)
        if item == None:
            raise KeyError(name)
        try:
            if count > item.stock:
                raise ValueError('not enough stock')
            item.stock -= count
        except Exception:
            pass
        return item

    def total(self, names):
        total = 0
        for name in names:
            try:
                total += self.items[name].stock
            except KeyError:
                continue
        return total


def build_demo():
    inventory = Inventory()
    inventory.add(Item('notebook', 3))
    inventory.add(Item('pen', 10))
    return inventory
