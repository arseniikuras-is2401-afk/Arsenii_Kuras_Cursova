"""Статуси замовлення за патерном «Стан».

Кожен статус — окремий клас, який знає, куди з нього можна перейти, що
перевірити перед входом і що змінити в замовленні при вході. Замовлення
лише делегує цю поведінку поточному стану, тож у ньому немає ланцюжків
if/elif за статусами.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from models.errors import BusinessRuleError

if TYPE_CHECKING:
    from models.order import Order


class OrderStatus(Enum):
    """Значення статусу, яке зберігається в базі."""

    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAID = "paid"
    CANCELLED = "cancelled"

    @property
    def state(self) -> "OrderState":
        return _STATES[self]

    @property
    def title(self) -> str:
        return self.state.title


class OrderState(ABC):
    """Поведінка замовлення в певному статусі."""

    status: OrderStatus
    title: str
    lines_editable = False   # чи можна змінювати роботи й запчастини
    is_open = False          # замовлення ще в роботі (впливає на ліміти)
    can_delete = False       # чи дозволено видалити замовлення

    @abstractmethod
    def allowed_next(self) -> frozenset[OrderStatus]:
        """Статуси, в які можна перейти з поточного."""

    def can_switch_to(self, status: OrderStatus) -> bool:
        return status in self.allowed_next()

    def check_enter(self, order: "Order"):
        """Перевірки перед входом у статус; за замовчуванням їх немає."""

    def on_enter(self, order: "Order", moment: datetime):
        """Зміни замовлення при вході в статус; за замовчуванням їх немає."""

    def locked_reason(self) -> str:
        """Пояснення для неактивних кнопок зміни рядків."""
        return f"Замовлення у статусі «{self.title}» змінювати не можна"


class NewState(OrderState):
    status = OrderStatus.NEW
    title = "Нове"
    lines_editable = True
    is_open = True
    can_delete = True

    def allowed_next(self) -> frozenset[OrderStatus]:
        return frozenset({OrderStatus.IN_PROGRESS, OrderStatus.CANCELLED})


class InProgressState(OrderState):
    status = OrderStatus.IN_PROGRESS
    title = "В роботі"
    lines_editable = True
    is_open = True

    def allowed_next(self) -> frozenset[OrderStatus]:
        return frozenset({OrderStatus.COMPLETED, OrderStatus.CANCELLED})

    def check_enter(self, order: "Order"):
        if not order.work_lines():
            raise BusinessRuleError(
                "Додайте хоча б одну роботу, щоб почати ремонт")

    def on_enter(self, order: "Order", moment: datetime):
        # Повернення на доопрацювання скасовує попередню дату завершення.
        order.clear_completion()


class CompletedState(OrderState):
    status = OrderStatus.COMPLETED
    title = "Виконано"

    def allowed_next(self) -> frozenset[OrderStatus]:
        return frozenset({OrderStatus.IN_PROGRESS, OrderStatus.PAID})

    def check_enter(self, order: "Order"):
        if not order.work_lines():
            raise BusinessRuleError(
                "Не можна завершити замовлення без жодної роботи")

    def on_enter(self, order: "Order", moment: datetime):
        order.mark_completed(moment)


class PaidState(OrderState):
    status = OrderStatus.PAID
    title = "Оплачено"

    def allowed_next(self) -> frozenset[OrderStatus]:
        return frozenset()

    def on_enter(self, order: "Order", moment: datetime):
        order.mark_paid(moment)

    def locked_reason(self) -> str:
        return "Оплачене замовлення змінювати не можна"


class CancelledState(OrderState):
    status = OrderStatus.CANCELLED
    title = "Скасовано"
    can_delete = True

    def allowed_next(self) -> frozenset[OrderStatus]:
        return frozenset()

    def on_enter(self, order: "Order", moment: datetime):
        # Рядки лишаються в замовленні для історії, а запчастини — на склад.
        order.release_all_parts()


_STATES: dict[OrderStatus, OrderState] = {
    state.status: state
    for state in (NewState(), InProgressState(), CompletedState(),
                  PaidState(), CancelledState())
}
