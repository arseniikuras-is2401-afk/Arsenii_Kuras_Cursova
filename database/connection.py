"""Підключення до SQLite: одне з'єднання на весь час роботи застосунку."""

import sqlite3
from pathlib import Path

MEMORY = ":memory:"


def _unicode_lower(value):
    """LOWER() у SQLite змінює регістр лише латиниці, тому кирилицю зводимо
    до нижнього регістру функцією Python, зареєстрованою як ulower()."""
    return value.lower() if isinstance(value, str) else value


class Database:
    """Створює, налаштовує й закриває з'єднання з файлом бази.

    Також стежить, щоб одиниці роботи (транзакції) не вкладались одна в одну:
    вкладена одиниця підтвердила б частину чужої операції.
    """

    def __init__(self, path: Path | str):
        self._path = path if path == MEMORY else Path(path)
        self._connection: sqlite3.Connection | None = None
        self._unit_active = False

    @property
    def path(self) -> Path | str:
        return self._path

    def connection(self) -> sqlite3.Connection:
        """Повертає з'єднання, відкриваючи його під час першого звернення."""
        if self._connection is None:
            self._connection = self._open()
        return self._connection

    def close(self):
        if self._connection is not None:
            self._connection.rollback()
            self._connection.close()
            self._connection = None

    def begin_unit(self):
        if self._unit_active:
            raise RuntimeError("Вкладені одиниці роботи не підтримуються: "
                               "завершіть поточну транзакцію")
        self._unit_active = True

    def end_unit(self):
        self._unit_active = False

    def _open(self) -> sqlite3.Connection:
        if self._path != MEMORY:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        # PRAGMA foreign_keys не діє всередині відкритої транзакції, тому
        # з'єднання спершу відкривається в режимі autocommit=True.
        connection = sqlite3.connect(self._path, autocommit=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.create_function("ulower", 1, _unicode_lower,
                                   deterministic=True)
        # Далі кожна зміна відбувається лише в явній транзакції: commit()
        # або rollback() викликає UnitOfWork (Python 3.12+).
        connection.autocommit = False
        return connection
