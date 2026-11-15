"""Базовий клас доступу до однієї таблиці."""

import sqlite3
from abc import ABC, abstractmethod
from typing import ClassVar

from database.query import ListQuery, SortKey, escape_like, resolve_field
from models.errors import NotFoundError


class TableDao(ABC):
    """Спільні операції: читання за id, вибірка за ListQuery, видалення.

    Нащадок описує свою таблицю атрибутами класу:
    TABLE / PK          — таблиця й первинний ключ;
    LIST_SOURCE         — таблиця або представлення для списків;
    FIELDS              — білий список «поле → SQL-вираз» для фільтрів і
                          сортування;
    SEARCH_FIELDS       — поля, в яких шукає рядок пошуку;
    DEFAULT_SORT        — порядок, якщо користувач його не задав;
    USAGES              — запити, що рахують посилання на запис (для
                          пояснення, чому його не можна видалити).
    DAO ніколи не викликає commit(): межі транзакції задає UnitOfWork.
    """

    TABLE: ClassVar[str]
    PK: ClassVar[str]
    LIST_SOURCE: ClassVar[str]
    FIELDS: ClassVar[dict[str, str]]
    SEARCH_FIELDS: ClassVar[tuple[str, ...]] = ()
    DEFAULT_SORT: ClassVar[tuple[SortKey, ...]] = ()
    USAGES: ClassVar[tuple[tuple[str, str], ...]] = ()
    NOT_FOUND: ClassVar[str] = "Запис не знайдено; можливо, його вже видалено"

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    # ---- читання ------------------------------------------------------------

    def get(self, record_id: int):
        """Об'єкт моделі за id або NotFoundError."""
        return self._to_entity(self.get_row(record_id))

    def get_row(self, record_id: int) -> sqlite3.Row:
        row = self._connection.execute(
            f"SELECT * FROM {self.TABLE} WHERE {self.PK} = ?",
            (record_id,)).fetchone()
        if row is None:
            raise NotFoundError(self.NOT_FOUND)
        return row

    def find(self, query: ListQuery | None = None) -> list[sqlite3.Row]:
        """Рядки LIST_SOURCE з урахуванням пошуку, фільтрів і сортування."""
        sql, params = self.build_select(query or ListQuery())
        return self._connection.execute(sql, params).fetchall()

    def count(self, query: ListQuery | None = None) -> int:
        sql, params = self.build_select(query or ListQuery(), count_only=True)
        return self._connection.execute(sql, params).fetchone()[0]

    def find_duplicate(self, column: str, value,
                       exclude_id: int | None = None) -> sqlite3.Row | None:
        """Інший запис із таким самим значенням унікального стовпця."""
        if column not in self._unique_columns():
            raise ValueError(f"Стовпець {column} не є унікальним")
        sql = f"SELECT * FROM {self.TABLE} WHERE {column} = ?"
        params: list = [value]
        if exclude_id is not None:
            sql += f" AND {self.PK} <> ?"
            params.append(exclude_id)
        return self._connection.execute(sql, params).fetchone()

    def usages(self, record_id: int) -> list[str]:
        """Пояснення на кшталт «автомобілів: 2», якщо на запис є посилання."""
        found = []
        for sql, label in self.USAGES:
            amount = self._connection.execute(sql, (record_id,)).fetchone()[0]
            if amount:
                found.append(f"{label}: {amount}")
        return found

    # ---- зміна --------------------------------------------------------------

    def delete(self, record_id: int):
        cursor = self._connection.execute(
            f"DELETE FROM {self.TABLE} WHERE {self.PK} = ?", (record_id,))
        if cursor.rowcount == 0:
            raise NotFoundError(self.NOT_FOUND)

    def _insert(self, values: dict) -> int:
        columns = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        cursor = self._connection.execute(
            f"INSERT INTO {self.TABLE} ({columns}) VALUES ({marks})",
            list(values.values()))
        return cursor.lastrowid

    def _update(self, record_id: int, values: dict):
        assignments = ", ".join(f"{column} = ?" for column in values)
        cursor = self._connection.execute(
            f"UPDATE {self.TABLE} SET {assignments} WHERE {self.PK} = ?",
            [*values.values(), record_id])
        if cursor.rowcount == 0:
            raise NotFoundError(self.NOT_FOUND)

    # ---- побудова запиту ---------------------------------------------

    def build_select(self, query: ListQuery,
                     count_only: bool = False) -> tuple[str, list]:
        conditions, params = [], []
        search = query.search_text.strip().lower()
        if search and self.SEARCH_FIELDS:
            pattern = f"%{escape_like(search)}%"
            alternatives = [
                f"ulower({resolve_field(self.FIELDS, name)}) "
                f"LIKE ? ESCAPE '\\'"
                for name in self.SEARCH_FIELDS]
            conditions.append("(" + " OR ".join(alternatives) + ")")
            params.extend([pattern] * len(alternatives))
        for criterion in query.criteria:
            fragment, fragment_params = criterion.to_sql(self.FIELDS)
            if fragment:
                conditions.append(fragment)
                params.extend(fragment_params)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        if count_only:
            return f"SELECT count(*) FROM {self.LIST_SOURCE}{where}", params
        order_by = self.order_by(query.sort_keys)
        sql = (f"SELECT * FROM {self.LIST_SOURCE}{where} "
               f"ORDER BY {order_by}")
        return sql, params

    def order_by(self, sort_keys: list[SortKey]) -> str:
        """ORDER BY лише з дозволених полів; первинний ключ — останнім, щоб
        порядок рядків з однаковими значеннями був стабільним."""
        keys = list(sort_keys) or list(self.DEFAULT_SORT)
        parts = [
            f"{resolve_field(self.FIELDS, key.field)} "
            f"{'DESC' if key.descending else 'ASC'}"
            for key in keys]
        parts.append(f"{self.PK} ASC")
        return ", ".join(parts)

    def _unique_columns(self) -> set[str]:
        """Стовпці з UNIQUE-обмеженням (за індексами SQLite)."""
        columns = set()
        for index in self._connection.execute(
                f"PRAGMA index_list({self.TABLE})"):
            if index["unique"] and index["origin"] == "u":
                info = self._connection.execute(
                    f"PRAGMA index_info({index['name']})").fetchall()
                if len(info) == 1:
                    columns.add(info[0]["name"])
        return columns

    @abstractmethod
    def _to_entity(self, row: sqlite3.Row):
        """Перетворює рядок таблиці на об'єкт моделі."""
