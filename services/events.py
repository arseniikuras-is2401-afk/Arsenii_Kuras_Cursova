"""Сповіщення про зміну даних (патерн «Спостерігач») без залежності від Qt."""

from collections.abc import Callable, Iterable
from enum import Enum


class Topic(Enum):
    """Яка частина даних змінилась."""

    CLIENTS = "clients"
    CARS = "cars"
    STAFF = "staff"
    CATALOG = "catalog"
    STOCK = "stock"
    ORDERS = "orders"


Listener = Callable[[frozenset[Topic]], None]


class EventHub:
    """Розсилає теми змін тим, хто на них підписався.

    Сервіси публікують події лише після успішного commit(), тож підписники
    ніколи не оновлюються через операцію, яка не відбулася.
    """

    def __init__(self):
        self._subscriptions: list[tuple[frozenset[Topic], Listener]] = []

    def subscribe(self, topics: Iterable[Topic], listener: Listener):
        self._subscriptions.append((frozenset(topics), listener))

    def unsubscribe(self, listener: Listener):
        self._subscriptions = [item for item in self._subscriptions
                               if item[1] is not listener]

    def publish(self, *topics: Topic):
        """Кожен підписник отримує подію один раз, навіть якщо його
        стосуються кілька тем одразу."""
        changed = frozenset(topics)
        for wanted, listener in list(self._subscriptions):
            if wanted & changed:
                listener(changed)
