"""Опис вибірки для таблиць: пошук, умови фільтра, сортування.

Умови — поліморфні класи: кожна сама будує свій фрагмент WHERE. Назви полів
підставляються лише з білого списку DAO (FIELDS), значення — тільки через
параметри «?», тож введений текст ніколи не потрапляє в SQL напряму.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field

SqlFragment = tuple[str, list]


def resolve_field(fields: Mapping[str, str], name: str) -> str:
    """SQL-вираз для поля або ValueError, якщо поле не дозволене."""
    try:
        return fields[name]
    except KeyError:
        raise ValueError(f"Поле «{name}» не можна використовувати у вибірці") \
            from None


class Criterion(ABC):
    """Одна умова фільтра."""

    def __init__(self, field_name: str):
        self.field = field_name

    @abstractmethod
    def to_sql(self, fields: Mapping[str, str]) -> SqlFragment:
        """Фрагмент WHERE і його параметри; порожній рядок — умова не діє."""


class Equals(Criterion):
    """Поле дорівнює значенню (None → IS NULL)."""

    def __init__(self, field_name: str, value):
        super().__init__(field_name)
        self.value = value

    def to_sql(self, fields: Mapping[str, str]) -> SqlFragment:
        expression = resolve_field(fields, self.field)
        if self.value is None:
            return f"({expression}) IS NULL", []
        return f"({expression}) = ?", [self.value]


class Between(Criterion):
    """Поле в межах [low, high]; будь-яку межу можна не задавати."""

    def __init__(self, field_name: str, low=None, high=None):
        super().__init__(field_name)
        self.low = low
        self.high = high

    def to_sql(self, fields: Mapping[str, str]) -> SqlFragment:
        expression = resolve_field(fields, self.field)
        parts, params = [], []
        if self.low is not None:
            parts.append(f"({expression}) >= ?")
            params.append(self.low)
        if self.high is not None:
            parts.append(f"({expression}) <= ?")
            params.append(self.high)
        return " AND ".join(parts), params


class IsTrue(Criterion):
    """Логічна ознака (0/1) увімкнена: «лише прострочені», «нижче мінімуму»."""

    def to_sql(self, fields: Mapping[str, str]) -> SqlFragment:
        return f"({resolve_field(fields, self.field)}) <> 0", []


@dataclass(frozen=True)
class SortKey:
    """Поле сортування й напрямок."""

    field: str
    descending: bool = False


@dataclass
class ListQuery:
    """Що показати в таблиці.

    Порожній запит — усі записи в типовому порядку.
    """

    search_text: str = ""
    criteria: list[Criterion] = field(default_factory=list)
    sort_keys: list[SortKey] = field(default_factory=list)


def escape_like(text: str) -> str:
    """Екранує % і _ , щоб їх можна було шукати як звичайні символи."""
    return (text.replace("\\", "\\\\").replace("%", "\\%")
            .replace("_", "\\_"))
