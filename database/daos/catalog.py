"""Доступ до довідників: категорії, прайс робіт, запчастини, механіки."""

import sqlite3

from database.base_dao import TableDao
from database.query import SortKey
from models.catalog import Part, RepairCategory, WorkType
from models.money import Money
from models.person import Employee
from models.validators import format_date


class CategoryDao(TableDao):
    TABLE = "repair_categories"
    PK = "category_id"
    LIST_SOURCE = "v_category_list"
    FIELDS = {
        "category_id": "category_id",
        "name": "name",
        "work_types_count": "work_types_count",
        "parts_count": "parts_count",
    }
    SEARCH_FIELDS = ("name",)
    DEFAULT_SORT = (SortKey("name"),)
    USAGES = (
        ("SELECT count(*) FROM work_types WHERE category_id = ?",
         "робіт у прайсі"),
        ("SELECT count(*) FROM parts WHERE category_id = ?", "запчастин"),
    )
    NOT_FOUND = "Категорію не знайдено"

    def insert(self, category: RepairCategory) -> int:
        category.category_id = self._insert({"name": category.name})
        return category.category_id

    def update(self, category: RepairCategory):
        self._update(category.category_id, {"name": category.name})

    def all(self) -> list[RepairCategory]:
        return [self._to_entity(row) for row in self.find()]

    def _to_entity(self, row: sqlite3.Row) -> RepairCategory:
        return RepairCategory(row["name"], category_id=row["category_id"])


class _WithCategory(TableDao):
    """Спільне для таблиць, що посилаються на категорію ремонту."""

    def __init__(self, connection: sqlite3.Connection,
                 categories: CategoryDao):
        super().__init__(connection)
        self._categories = categories

    def _category(self, category_id: int | None) -> RepairCategory | None:
        return self._categories.get(category_id) if category_id else None


class WorkTypeDao(_WithCategory):
    TABLE = "work_types"
    PK = "work_type_id"
    LIST_SOURCE = "v_work_type_list"
    FIELDS = {
        "work_type_id": "work_type_id",
        "category_id": "category_id",
        "category_name": "category_name",
        "name": "name",
        "price_kop": "price_kop",
        "norm_hours": "norm_hours",
        "is_active": "is_active",
        "times_used": "times_used",
    }
    SEARCH_FIELDS = ("name", "category_name")
    DEFAULT_SORT = (SortKey("category_name"), SortKey("name"))
    USAGES = (("SELECT count(*) FROM order_works WHERE work_type_id = ?",
               "рядків у замовленнях"),)
    NOT_FOUND = "Роботу не знайдено в прайсі"

    def insert(self, work_type: WorkType) -> int:
        work_type.work_type_id = self._insert(self._values(work_type))
        return work_type.work_type_id

    def update(self, work_type: WorkType):
        self._update(work_type.work_type_id, self._values(work_type))

    def _values(self, work_type: WorkType) -> dict:
        return {
            "category_id": work_type.category.category_id,
            "name": work_type.name,
            "price_kop": work_type.price.kop,
            "norm_hours": work_type.norm_hours,
            "is_active": int(work_type.is_active),
        }

    def _to_entity(self, row: sqlite3.Row) -> WorkType:
        return WorkType(self._category(row["category_id"]), row["name"],
                        Money(row["price_kop"]), row["norm_hours"],
                        is_active=bool(row["is_active"]),
                        work_type_id=row["work_type_id"])


class PartDao(_WithCategory):
    TABLE = "parts"
    PK = "part_id"
    LIST_SOURCE = "v_part_list"
    FIELDS = {
        "part_id": "part_id",
        "category_id": "category_id",
        "category_name": "category_name",
        "article": "article",
        "name": "name",
        "price_kop": "price_kop",
        "stock_qty": "stock_qty",
        "min_qty": "min_qty",
        "is_low": "is_low",
    }
    SEARCH_FIELDS = ("article", "name")
    DEFAULT_SORT = (SortKey("name"),)
    USAGES = (("SELECT count(*) FROM order_parts WHERE part_id = ?",
               "рядків у замовленнях"),)
    NOT_FOUND = "Запчастину не знайдено"

    def insert(self, part: Part) -> int:
        values = self._values(part)
        values["stock_qty"] = part.stock_qty
        part.part_id = self._insert(values)
        return part.part_id

    def update(self, part: Part):
        """Оновлює картку запчастини; залишок змінює лише update_stock()."""
        self._update(part.part_id, self._values(part))

    def update_stock(self, part: Part):
        self._update(part.part_id, {"stock_qty": part.stock_qty})

    def find_by_article(self, article: str) -> Part | None:
        row = self.find_duplicate("article", article)
        return self._to_entity(row) if row else None

    def _values(self, part: Part) -> dict:
        return {
            "category_id": part.category.category_id,
            "article": part.article,
            "name": part.name,
            "price_kop": part.price.kop,
            "min_qty": part.min_qty,
        }

    def _to_entity(self, row: sqlite3.Row) -> Part:
        return Part(self._category(row["category_id"]), row["article"],
                    row["name"], Money(row["price_kop"]),
                    stock_qty=row["stock_qty"], min_qty=row["min_qty"],
                    part_id=row["part_id"])


class EmployeeDao(_WithCategory):
    TABLE = "employees"
    PK = "employee_id"
    LIST_SOURCE = "v_employee_list"
    FIELDS = {
        "employee_id": "employee_id",
        "full_name": "full_name",
        "last_name": "last_name",
        "phone": "phone",
        "category_id": "category_id",
        "category_name": "coalesce(category_name, '')",
        "hired_on": "hired_on",
        "is_active": "is_active",
        "open_orders": "open_orders",
        "total_orders": "total_orders",
    }
    SEARCH_FIELDS = ("full_name", "phone")
    DEFAULT_SORT = (SortKey("is_active", descending=True),
                    SortKey("last_name"))
    USAGES = (("SELECT count(*) FROM orders WHERE employee_id = ?",
               "замовлень"),)
    NOT_FOUND = "Механіка не знайдено"

    def insert(self, employee: Employee) -> int:
        employee.employee_id = self._insert(self._values(employee))
        return employee.employee_id

    def update(self, employee: Employee):
        self._update(employee.employee_id, self._values(employee))

    def open_orders_count(self, employee_id: int) -> int:
        return self._connection.execute(
            "SELECT count(*) FROM orders WHERE employee_id = ? "
            "AND status IN ('new', 'in_progress')",
            (employee_id,)).fetchone()[0]

    def _values(self, employee: Employee) -> dict:
        specialization = employee.specialization
        return {
            "last_name": employee.last_name,
            "first_name": employee.first_name,
            "phone": employee.phone,
            "category_id": specialization.category_id if specialization
            else None,
            "hired_on": format_date(employee.hired_on),
            "is_active": int(employee.is_active),
        }

    def _to_entity(self, row: sqlite3.Row) -> Employee:
        return Employee(row["last_name"], row["first_name"], row["phone"],
                        hired_on=row["hired_on"],
                        specialization=self._category(row["category_id"]),
                        is_active=bool(row["is_active"]),
                        employee_id=row["employee_id"])
