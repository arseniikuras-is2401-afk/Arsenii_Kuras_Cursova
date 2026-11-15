"""Одиниця роботи: одна завершена дія користувача = одна транзакція."""

import sqlite3

from database.connection import Database
from database.daos import (CarDao, CategoryDao, ClientDao, EmployeeDao,
                           OrderDao, PartDao, ReportDao, WorkTypeDao)
from models.errors import (AutoServiceError, BusinessRuleError,
                           RecordInUseError, ValidationError)

# Повідомлення для порушень UNIQUE: «таблиця.стовпець» → (поле, текст).
_UNIQUE_MESSAGES = {
    "clients.phone": ("phone", "Клієнт з таким телефоном уже є в базі"),
    "clients.email": ("email", "Клієнт з таким email уже є в базі"),
    "cars.plate_number": ("plate_number",
                          "Авто з таким держномером уже є в базі"),
    "cars.vin": ("vin", "Авто з таким VIN уже є в базі"),
    "employees.phone": ("phone", "Механік з таким телефоном уже є в базі"),
    "repair_categories.name": ("name", "Така категорія вже існує"),
    "work_types.name": ("name", "Робота з такою назвою вже є в прайсі"),
    "parts.article": ("article", "Запчастина з таким артикулом уже є"),
}


def translate_integrity_error(error: sqlite3.IntegrityError) \
        -> AutoServiceError:
    """Перекладає повідомлення SQLite на зрозуміле користувачеві.

    Обмеження бази — друга лінія захисту: зазвичай моделі й сервіси
    перевіряють дані раніше, але якщо запит усе ж порушив обмеження,
    користувач побачить пояснення, а не технічний текст.
    """
    text = str(error)
    if text.startswith("UNIQUE constraint failed:"):
        key = text.split(":", 1)[1].strip()
        if key in _UNIQUE_MESSAGES:
            field, message = _UNIQUE_MESSAGES[key]
            return ValidationError(message, field=field)
        return ValidationError("Такий запис уже існує")
    if text.startswith("FOREIGN KEY constraint failed"):
        return RecordInUseError(
            "Запис пов'язаний з іншими даними, тому операцію не виконано")
    if text.startswith("CHECK constraint failed"):
        return BusinessRuleError(
            "Значення порушує обмеження бази даних; операцію не виконано")
    return BusinessRuleError(f"Помилка цілісності даних: {text}")


class UnitOfWork:
    """Контекстний менеджер транзакції з набором DAO на одному з'єднанні.

        with UnitOfWork(database) as uow:
            part = uow.parts.get(5)
            ...
        # вихід без винятку — commit(), з винятком — rollback()

    Жоден DAO не викликає commit() сам, тому частина операції не може
    зберегтися окремо від решти.
    """

    def __init__(self, database: Database):
        self._database = database
        self._connection = database.connection()
        self.clients = ClientDao(self._connection)
        self.cars = CarDao(self._connection, self.clients)
        self.categories = CategoryDao(self._connection)
        self.employees = EmployeeDao(self._connection, self.categories)
        self.work_types = WorkTypeDao(self._connection, self.categories)
        self.parts = PartDao(self._connection, self.categories)
        self.orders = OrderDao(self._connection, self.cars, self.employees,
                               self.work_types, self.parts)
        self.reports = ReportDao(self._connection)

    def __enter__(self) -> "UnitOfWork":
        self._database.begin_unit()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        try:
            if exc_type is None:
                try:
                    self._connection.commit()
                except sqlite3.IntegrityError as error:
                    self._connection.rollback()
                    raise translate_integrity_error(error) from error
            else:
                self._connection.rollback()
                if isinstance(exc, sqlite3.IntegrityError):
                    raise translate_integrity_error(exc) from exc
        finally:
            self._database.end_unit()
        return False
