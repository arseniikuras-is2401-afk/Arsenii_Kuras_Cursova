"""Доступ до замовлень, їхніх рядків та історії статусів."""

import sqlite3
from datetime import datetime

from database.base_dao import TableDao
from database.daos.catalog import EmployeeDao, PartDao, WorkTypeDao
from database.daos.clients import CarDao
from database.query import SortKey
from models.money import Money
from models.order import Order
from models.order_lines import LineKind, OrderLine, PartLine, WorkLine
from models.order_state import OrderStatus
from models.validators import format_date, format_datetime


class OrderDao(TableDao):
    TABLE = "orders"
    PK = "order_id"
    LIST_SOURCE = "v_order_list"
    FIELDS = {
        "order_id": "order_id",
        "order_number": "order_number",
        "car_id": "car_id",
        "client_id": "client_id",
        "employee_id": "employee_id",
        "status": "status",
        "accepted_at": "accepted_at",
        "accepted_on": "date(accepted_at)",
        "due_date": "due_date",
        "completed_at": "coalesce(completed_at, '')",
        "paid_at": "coalesce(paid_at, '')",
        "paid_on": "date(paid_at)",
        "plate_number": "plate_number",
        "car_title": "car_title",
        "make": "make",
        "client_name": "client_name",
        "client_phone": "client_phone",
        "mechanic_name": "mechanic_name",
        "complaint": "complaint",
        "works_kop": "works_kop",
        "parts_kop": "parts_kop",
        "discount_kop": "discount_kop",
        "total_kop": "total_kop",
        "labor_hours": "labor_hours",
        "is_overdue": "is_overdue",
        "is_open": "status IN ('new', 'in_progress')",
    }
    SEARCH_FIELDS = ("order_number", "plate_number", "client_name",
                     "client_phone", "car_title")
    DEFAULT_SORT = (SortKey("accepted_at", descending=True),)
    NOT_FOUND = "Замовлення не знайдено; можливо, його вже видалено"

    def __init__(self, connection: sqlite3.Connection, cars: CarDao,
                 employees: EmployeeDao, work_types: WorkTypeDao,
                 parts: PartDao):
        super().__init__(connection)
        self._cars = cars
        self._employees = employees
        self._work_types = work_types
        self._parts = parts

    # ---- шапка ------------------------------------------------------------

    def insert(self, order: Order) -> int:
        values = self._header_values(order)
        values.update(self._status_values(order))
        values["car_id"] = order.car.car_id
        values["accepted_at"] = format_datetime(order.accepted_at)
        values["intake_mileage_km"] = order.intake_mileage_km
        values["loyalty_discount_pct"] = order.loyalty_discount_pct
        order.order_id = self._insert(values)
        return order.order_id

    def update_header(self, order: Order):
        """Механік, термін, скарга, ручна знижка."""
        self._update(order.order_id, self._header_values(order))

    def update_status(self, order: Order):
        self._update(order.order_id, self._status_values(order))

    def log_status(self, order_id: int, old: OrderStatus | None,
                   new: OrderStatus, moment: datetime,
                   comment: str | None = None):
        self._connection.execute(
            "INSERT INTO order_status_log "
            "(order_id, old_status, new_status, changed_at, comment) "
            "VALUES (?, ?, ?, ?, ?)",
            (order_id, old.value if old else None, new.value,
             format_datetime(moment), comment))

    def status_history(self, order_id: int) -> list[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM order_status_log WHERE order_id = ? "
            "ORDER BY changed_at, log_id", (order_id,)).fetchall()

    # ---- рядки --------------------------------------------------------------

    def insert_line(self, order: Order, line: OrderLine) -> int:
        table, item_column, item_id = self._line_target(line)
        cursor = self._connection.execute(
            f"INSERT INTO {table} (order_id, {item_column}, quantity, "
            f"unit_price_kop) VALUES (?, ?, ?, ?)",
            (order.order_id, item_id, line.quantity, line.unit_price.kop))
        line.line_id = cursor.lastrowid
        return line.line_id

    def update_line_quantity(self, line: OrderLine):
        table, _, _ = self._line_target(line)
        pk = "order_work_id" if line.kind() is LineKind.WORK \
            else "order_part_id"
        self._connection.execute(
            f"UPDATE {table} SET quantity = ? WHERE {pk} = ?",
            (line.quantity, line.line_id))

    def delete_line(self, line: OrderLine):
        table, _, _ = self._line_target(line)
        pk = "order_work_id" if line.kind() is LineKind.WORK \
            else "order_part_id"
        self._connection.execute(f"DELETE FROM {table} WHERE {pk} = ?",
                                 (line.line_id,))

    def save_line(self, order: Order, line: OrderLine):
        """Новий рядок вставляє, наявний (повторна запчастина) — оновлює."""
        if line.line_id is None:
            self.insert_line(order, line)
        else:
            self.update_line_quantity(line)

    # ---- службове ---------------------------------------------------------

    def _to_entity(self, row: sqlite3.Row) -> Order:
        order = Order(
            self._cars.get(row["car_id"]),
            self._employees.get(row["employee_id"]),
            row["complaint"], row["due_date"],
            accepted_at=row["accepted_at"],
            intake_mileage_km=row["intake_mileage_km"],
            manual_discount_pct=row["manual_discount_pct"],
            loyalty_discount_pct=row["loyalty_discount_pct"],
            status=OrderStatus(row["status"]),
            completed_at=row["completed_at"], paid_at=row["paid_at"],
            order_id=row["order_id"])
        for line_row in self._connection.execute(
                "SELECT * FROM order_works WHERE order_id = ? "
                "ORDER BY order_work_id", (order.order_id,)):
            order.restore_line(WorkLine(
                self._work_types.get(line_row["work_type_id"]),
                line_row["quantity"], Money(line_row["unit_price_kop"]),
                line_id=line_row["order_work_id"]))
        for line_row in self._connection.execute(
                "SELECT * FROM order_parts WHERE order_id = ? "
                "ORDER BY order_part_id", (order.order_id,)):
            order.restore_line(PartLine(
                self._parts.get(line_row["part_id"]),
                line_row["quantity"], Money(line_row["unit_price_kop"]),
                line_id=line_row["order_part_id"]))
        return order

    @staticmethod
    def _header_values(order: Order) -> dict:
        return {
            "employee_id": order.mechanic.employee_id,
            "due_date": format_date(order.due_date),
            "complaint": order.complaint,
            "manual_discount_pct": order.manual_discount_pct,
        }

    @staticmethod
    def _status_values(order: Order) -> dict:
        return {
            "status": order.status.value,
            "completed_at": format_datetime(order.completed_at),
            "paid_at": format_datetime(order.paid_at),
        }

    @staticmethod
    def _line_target(line: OrderLine) -> tuple[str, str, int]:
        if isinstance(line, WorkLine):
            return "order_works", "work_type_id", line.work_type.work_type_id
        return "order_parts", "part_id", line.part.part_id
