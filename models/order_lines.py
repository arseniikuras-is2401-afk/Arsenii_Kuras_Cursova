"""Рядки замовлення: виконані роботи й використані запчастини."""

from abc import ABC, abstractmethod
from enum import Enum

from config import MAX_PART_QUANTITY, MAX_WORK_QUANTITY
from models.catalog import Part, WorkType
from models.money import Money
from models.validators import check_int_range


class LineKind(Enum):
    """Вид рядка; від нього залежить, які знижки діють."""

    WORK = "work"
    PART = "part"


class OrderLine(ABC):
    """Рядок замовлення з ціною, зафіксованою в момент додавання.

    Зміна прайсу пізніше не змінює суми вже оформлених замовлень.
    """

    MAX_QUANTITY = 1

    def __init__(self, quantity: int, unit_price: Money,
                 line_id: int | None = None):
        self.line_id = line_id
        self.quantity = quantity
        self.unit_price = unit_price

    @property
    def quantity(self) -> int:
        return self._quantity

    @quantity.setter
    def quantity(self, value: int):
        self._quantity = check_int_range(value, 1, self.MAX_QUANTITY,
                                         "quantity", "Кількість")

    def total(self) -> Money:
        return self.unit_price * self.quantity

    @abstractmethod
    def kind(self) -> LineKind:
        """Вид рядка."""

    @abstractmethod
    def title(self) -> str:
        """Назва для таблиці рядків."""

    @abstractmethod
    def labor_hours(self) -> float:
        """Нормо-години, які рядок додає механіку."""


class WorkLine(OrderLine):
    """Виконана робота з прайсу."""

    MAX_QUANTITY = MAX_WORK_QUANTITY

    def __init__(self, work_type: WorkType, quantity: int,
                 unit_price: Money | None = None, line_id: int | None = None):
        self.work_type = work_type
        super().__init__(quantity, unit_price or work_type.price, line_id)

    def kind(self) -> LineKind:
        return LineKind.WORK

    def title(self) -> str:
        return self.work_type.name

    def labor_hours(self) -> float:
        return round(self.work_type.norm_hours * self.quantity, 2)


class PartLine(OrderLine):
    """Запчастина, списана зі складу під замовлення."""

    MAX_QUANTITY = MAX_PART_QUANTITY

    def __init__(self, part: Part, quantity: int,
                 unit_price: Money | None = None, line_id: int | None = None):
        self.part = part
        super().__init__(quantity, unit_price or part.price, line_id)

    def kind(self) -> LineKind:
        return LineKind.PART

    def title(self) -> str:
        return f"{self.part.name} [{self.part.article}]"

    def labor_hours(self) -> float:
        return 0.0

    def release_stock(self):
        """Повертає всю кількість рядка на склад."""
        self.part.put_back(self.quantity)
