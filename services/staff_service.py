"""Механіки автосервісу."""

import sqlite3

from config import MAX_OPEN_ORDERS_PER_MECHANIC
from database import Equals, ListQuery
from models.errors import BusinessRuleError
from models.person import Employee
from services.base import AppService
from services.events import Topic

_STAFF_TOPICS = (Topic.STAFF, Topic.ORDERS)


class StaffService(AppService):
    """Облік механіків і їхнього навантаження."""

    def find(self, query: ListQuery | None = None) -> list[sqlite3.Row]:
        with self._unit() as uow:
            return uow.employees.find(query)

    def get(self, employee_id: int) -> Employee:
        with self._unit() as uow:
            return uow.employees.get(employee_id)

    def save(self, employee: Employee) -> int:
        def checks(uow):
            self._ensure_unique(uow.employees, "phone", employee.phone,
                                employee.employee_id,
                                "Механік з таким телефоном уже є в базі")
            if employee.employee_id is not None and not employee.is_active:
                self._ensure_no_open_orders(uow, employee.employee_id)
        return self._run_save("employees", employee, "employee_id", checks,
                              _STAFF_TOPICS)

    def set_active(self, employee_id: int, active: bool):
        """Деактивований механік лишається в історії, але не бере замовлень."""
        with self._unit() as uow:
            employee = uow.employees.get(employee_id)
            if not active:
                self._ensure_no_open_orders(uow, employee_id)
            employee.is_active = active
            uow.employees.update(employee)
        self._notify(*_STAFF_TOPICS)

    def delete(self, employee_id: int):
        with self._unit() as uow:
            self._ensure_not_used(
                uow.employees, employee_id, "Механіка",
                "Деактивуйте його: історія замовлень збережеться.")
            uow.employees.delete(employee_id)
        self._notify(*_STAFF_TOPICS)

    def available_mechanics(self, keep_id: int | None = None) \
            -> list[tuple[Employee, int]]:
        """Механіки, яким можна доручити замовлення, з їхнім навантаженням.

        `keep_id` — поточний механік замовлення: він лишається у списку,
        навіть якщо досяг ліміту, щоб форма редагування могла його показати.
        """
        query = ListQuery(criteria=[Equals("is_active", 1)])
        result = []
        with self._unit() as uow:
            for row in uow.employees.find(query):
                open_orders = row["open_orders"]
                if (open_orders < MAX_OPEN_ORDERS_PER_MECHANIC
                        or row["employee_id"] == keep_id):
                    result.append((uow.employees.get(row["employee_id"]),
                                   open_orders))
        return result

    @staticmethod
    def _ensure_no_open_orders(uow, employee_id: int):
        open_orders = uow.employees.open_orders_count(employee_id)
        if open_orders:
            raise BusinessRuleError(
                f"У механіка {open_orders} відкритих замовлень. Передайте їх "
                f"іншому механіку, а потім деактивуйте.")
