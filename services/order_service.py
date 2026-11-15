"""Замовлення-наряди: оформлення, роботи й запчастини, статуси."""

import sqlite3
from datetime import date

from config import (LOYALTY_DISCOUNT_PCT, LOYALTY_MIN_PAID_ORDERS,
                    MAX_OPEN_ORDERS_PER_MECHANIC)
from database import ListQuery, UnitOfWork
from models.errors import BusinessRuleError
from models.order import Order, format_order_number
from models.order_lines import LineKind, OrderLine, PartLine
from models.order_state import OrderStatus
from models.person import Employee
from services.base import AppService
from services.events import Topic

# Будь-яка зміна замовлення впливає на списки клієнтів, авто й механіків
# (ознаки «є відкрите замовлення», навантаження, кількість оплачених).
_ORDER_TOPICS = (Topic.ORDERS, Topic.CLIENTS, Topic.CARS, Topic.STAFF)


class OrderService(AppService):
    """Сценарії роботи із замовленнями; кожен — одна транзакція."""

    # ---- читання ------------------------------------------------------------

    def find(self, query: ListQuery | None = None) -> list[sqlite3.Row]:
        with self._unit() as uow:
            return uow.orders.find(query)

    def get(self, order_id: int) -> Order:
        with self._unit() as uow:
            return uow.orders.get(order_id)

    def history(self, order_id: int) -> list[sqlite3.Row]:
        with self._unit() as uow:
            return uow.orders.status_history(order_id)

    def loyalty_percent(self, client_id: int) -> int:
        """Знижка, яку клієнт отримає в новому замовленні."""
        with self._unit() as uow:
            return self._loyalty(uow, client_id)

    # ---- оформлення --------------------------------------------------------

    def create(self, car_id: int, employee_id: int, complaint: str,
               due_date: date, intake_mileage_km: int,
               manual_discount_pct: int = 0) -> int:
        """Оформлює замовлення; повертає його id."""
        with self._unit() as uow:
            car = uow.cars.get(car_id)
            open_id = uow.cars.open_order_id(car_id)
            if open_id is not None:
                raise BusinessRuleError(
                    f"Для {car.plate_number} уже є відкрите замовлення "
                    f"{format_order_number(open_id)}")
            mechanic = uow.employees.get(employee_id)
            self._ensure_mechanic_free(uow, mechanic)
            order = Order.open_new(
                car, mechanic, complaint, due_date, intake_mileage_km,
                manual_discount_pct=manual_discount_pct,
                loyalty_discount_pct=self._loyalty(uow, car.owner.client_id),
                accepted_at=self._now())
            uow.orders.insert(order)
            uow.orders.log_status(order.order_id, None, OrderStatus.NEW,
                                  order.accepted_at, "Замовлення оформлено")
        self._notify(*_ORDER_TOPICS)
        return order.order_id

    def update_header(self, order_id: int, employee_id: int, due_date: date,
                      complaint: str, manual_discount_pct: int):
        """Змінює механіка, термін, скаргу й ручну знижку."""
        with self._unit() as uow:
            order = uow.orders.get(order_id)
            if not order.state.lines_editable:
                raise BusinessRuleError(order.state.locked_reason())
            if employee_id != order.mechanic.employee_id:
                mechanic = uow.employees.get(employee_id)
                self._ensure_mechanic_free(uow, mechanic)
                order.mechanic = mechanic
            order.due_date = due_date
            order.complaint = complaint
            order.manual_discount_pct = manual_discount_pct
            uow.orders.update_header(order)
        self._notify(*_ORDER_TOPICS)

    # ---- рядки --------------------------------------------------------------

    def add_work(self, order_id: int, work_type_id: int,
                 quantity: int) -> OrderLine:
        with self._unit() as uow:
            order = uow.orders.get(order_id)
            line = order.add_work(uow.work_types.get(work_type_id), quantity)
            uow.orders.save_line(order, line)
        self._notify(*_ORDER_TOPICS)
        return line

    def add_part(self, order_id: int, part_id: int,
                 quantity: int) -> PartLine:
        """Списує запчастину зі складу в замовлення (рядок + залишок разом)."""
        with self._unit() as uow:
            order = uow.orders.get(order_id)
            line = order.add_part(uow.parts.get(part_id), quantity)
            uow.orders.save_line(order, line)
            uow.parts.update_stock(line.part)
        self._notify(*_ORDER_TOPICS, Topic.STOCK)
        return line

    def remove_line(self, order_id: int, kind: LineKind, line_id: int):
        """Прибирає рядок; запчастини повертаються на склад."""
        with self._unit() as uow:
            order = uow.orders.get(order_id)
            line = order.find_line(kind, line_id)
            order.remove_line(line)
            uow.orders.delete_line(line)
            if isinstance(line, PartLine):
                uow.parts.update_stock(line.part)
        self._notify(*_ORDER_TOPICS, Topic.STOCK)

    # ---- статус -------------------------------------------------------------

    def change_status(self, order_id: int, new_status: OrderStatus,
                      comment: str | None = None) -> Order:
        """Переводить замовлення в новий статус з усіма наслідками.

        Завершення оновлює пробіг авто, скасування повертає запчастини на
        склад; усе це й запис в історії — в одній транзакції.
        """
        moment = self._now()
        with self._unit() as uow:
            order = uow.orders.get(order_id)
            old_status = order.status
            order.change_status(new_status, moment)
            uow.orders.update_status(order)
            uow.orders.log_status(order_id, old_status, new_status, moment,
                                  (comment or "").strip() or None)
            if new_status is OrderStatus.COMPLETED:
                uow.cars.update_mileage(order.car)
            if new_status is OrderStatus.CANCELLED:
                self._save_stock(uow, order)
        self._notify(*_ORDER_TOPICS, Topic.STOCK)
        return order

    def delete(self, order_id: int):
        """Видаляє нове або скасоване замовлення.

        Для нового запчастини повертаються на склад; для скасованого вони
        вже повернулися під час скасування.
        """
        with self._unit() as uow:
            order = uow.orders.get(order_id)
            if not order.state.can_delete:
                raise BusinessRuleError(
                    "Видалити можна лише нове або скасоване замовлення. "
                    "Замовлення в роботі спершу скасуйте.")
            if order.status is OrderStatus.NEW:
                order.release_all_parts()
                self._save_stock(uow, order)
            uow.orders.delete(order_id)
        self._notify(*_ORDER_TOPICS, Topic.STOCK)

    # ---- допоміжне ----------------------------------------------------------

    @staticmethod
    def _loyalty(uow: UnitOfWork, client_id: int) -> int:
        paid = uow.clients.paid_orders_count(client_id)
        return LOYALTY_DISCOUNT_PCT if paid >= LOYALTY_MIN_PAID_ORDERS else 0

    @staticmethod
    def _ensure_mechanic_free(uow: UnitOfWork, mechanic: Employee):
        if not mechanic.is_active:
            raise BusinessRuleError(
                f"Механік {mechanic.full_name()} неактивний")
        load = uow.employees.open_orders_count(mechanic.employee_id)
        if load >= MAX_OPEN_ORDERS_PER_MECHANIC:
            raise BusinessRuleError(
                f"У механіка {mechanic.full_name()} уже {load} відкриті "
                f"замовлення (максимум {MAX_OPEN_ORDERS_PER_MECHANIC})")

    @staticmethod
    def _save_stock(uow: UnitOfWork, order: Order):
        for line in order.part_lines():
            uow.parts.update_stock(line.part)
