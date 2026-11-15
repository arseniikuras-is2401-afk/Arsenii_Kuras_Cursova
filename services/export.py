"""Експорт поточної вибірки таблиці в CSV або JSON."""

import csv
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from database import ListQuery
from models.errors import AutoServiceError, ValidationError
from models.money import Money
from models.order_state import OrderStatus
from models.validators import format_phone
from services.base import AppService


class ColumnKind(Enum):
    """Як показати значення стовпця у файлі."""

    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    MONEY = "money"        # копійки в базі → гривні у файлі
    BOOLEAN = "boolean"
    STATUS = "status"      # код статусу замовлення → назва українською
    PHONE = "phone"        # 0671234567 → «067 123 45 67»
    DATE = "date"          # «2026-11-14» → «14.11.2026»
    DATETIME = "datetime"  # «2026-11-14 09:30» → «14.11.2026 09:30»


@dataclass(frozen=True)
class ExportColumn:
    """Стовпець експорту: ключ рядка з бази, заголовок і вид значення."""

    key: str
    title: str
    kind: ColumnKind = ColumnKind.TEXT

    def csv_value(self, row: Mapping) -> str:
        """Значення для людини: «1234,50», «так», «В роботі»."""
        value = row[self.key]
        if value is None:
            return ""
        if self.kind is ColumnKind.MONEY:
            return Money(value).to_text(with_currency=False).replace(
                " ", "")
        if self.kind is ColumnKind.DECIMAL:
            return f"{value:g}".replace(".", ",")
        if self.kind is ColumnKind.BOOLEAN:
            return "так" if value else "ні"
        if self.kind is ColumnKind.STATUS:
            return OrderStatus(value).title
        if self.kind is ColumnKind.PHONE:
            return format_phone(value)
        if self.kind in (ColumnKind.DATE, ColumnKind.DATETIME):
            text = str(value)
            human = f"{text[8:10]}.{text[5:7]}.{text[:4]}"
            return f"{human} {text[11:16]}".strip() \
                if self.kind is ColumnKind.DATETIME else human
        return str(value)

    def json_value(self, row: Mapping):
        """Значення для програм: числа — числами, логічні — true/false."""
        value = row[self.key]
        if value is None:
            return None
        if self.kind is ColumnKind.MONEY:
            return float(Decimal(value) / 100)
        if self.kind is ColumnKind.BOOLEAN:
            return bool(value)
        return value


class Exporter(ABC):
    """Записує рядки у файл певного формату."""

    EXTENSION = ""
    DESCRIPTION = ""

    def export(self, columns: Sequence[ExportColumn],
               rows: Sequence[Mapping], path: Path):
        try:
            self._write(columns, rows, Path(path))
        except OSError as error:
            raise AutoServiceError(
                f"Не вдалося записати файл {Path(path).name}: "
                f"{error.strerror or error}") from error

    @abstractmethod
    def _write(self, columns: Sequence[ExportColumn],
               rows: Sequence[Mapping], path: Path):
        """Записує файл."""


class CsvExporter(Exporter):
    """CSV для Excel: UTF-8 з BOM (щоб коректно відкрилась кирилиця), «;»."""

    EXTENSION = ".csv"
    DESCRIPTION = "CSV для Excel (*.csv)"

    def _write(self, columns, rows, path):
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow([column.title for column in columns])
            for row in rows:
                writer.writerow([column.csv_value(row) for column in columns])


class JsonExporter(Exporter):
    """JSON: масив об'єктів з англійськими ключами полів."""

    EXTENSION = ".json"
    DESCRIPTION = "JSON (*.json)"

    def _write(self, columns, rows, path):
        data = [{column.key: column.json_value(row) for column in columns}
                for row in rows]
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)


EXPORTERS: tuple[Exporter, ...] = (CsvExporter(), JsonExporter())


def exporter_for(path: Path | str) -> Exporter:
    """Обирає експортер за розширенням файлу."""
    suffix = Path(path).suffix.lower()
    for exporter in EXPORTERS:
        if exporter.EXTENSION == suffix:
            return exporter
    raise ValidationError("Оберіть файл з розширенням .csv або .json",
                          field="path")


class ExportService(AppService):
    """Експортує те, що зараз показує таблиця: з пошуком, фільтрами й
    сортуванням."""

    SOURCES = ("clients", "cars", "employees", "categories", "work_types",
               "parts", "orders")

    def export(self, source: str, query: ListQuery,
               columns: Sequence[ExportColumn], path: Path | str) -> int:
        """Повертає кількість експортованих рядків."""
        if source not in self.SOURCES:
            raise ValueError(f"Невідоме джерело експорту: {source}")
        exporter = exporter_for(path)
        with self._unit() as uow:
            rows = getattr(uow, source).find(query)
        exporter.export(columns, rows, Path(path))
        return len(rows)
