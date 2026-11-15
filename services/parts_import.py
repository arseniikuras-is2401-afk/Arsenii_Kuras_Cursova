"""Імпорт приходу запчастин із CSV-накладної постачальника."""

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from models.catalog import Part
from models.errors import AutoServiceError, ValidationError
from models.money import Money
from models.validators import check_int_range, clean_text, normalize_article
from services.base import AppService
from services.events import Topic

MAX_ROWS = 5_000

# Заголовок у файлі (нижній регістр) → внутрішня назва поля.
HEADER_ALIASES = {
    "article": "article", "артикул": "article",
    "name": "name", "назва": "name",
    "category": "category", "категорія": "category",
    "price": "price", "ціна": "price", "ціна, грн": "price",
    "quantity": "quantity", "кількість": "quantity",
    "min_qty": "min_qty", "мінімальний залишок": "min_qty",
    "мін. залишок": "min_qty",
}
REQUIRED = ("article", "name", "category", "price", "quantity")
FIELD_TITLES = {"article": "Артикул", "name": "Назва",
                "category": "Категорія", "price": "Ціна",
                "quantity": "Кількість", "min_qty": "Мінімальний залишок"}


def _line_number(message: str) -> int:
    """Номер рядка з повідомлення «Рядок 12: …» (для впорядкування звіту)."""
    head = message.split(":", 1)[0]
    digits = "".join(char for char in head if char.isdigit())
    return int(digits) if digits else 0


@dataclass
class ReceiptLine:
    """Перевірений рядок накладної."""

    line_number: int
    article: str
    name: str
    category_name: str
    price: Money
    quantity: int
    min_qty: int | None


@dataclass
class ImportReport:
    """Підсумок імпорту для показу користувачу."""

    added: int = 0
    restocked: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def imported(self) -> int:
        return self.added + self.restocked

    def summary(self) -> str:
        lines = [f"Нових запчастин: {self.added}",
                 f"Поповнено наявних: {self.restocked}",
                 f"Рядків з помилками: {len(self.errors)}"]
        return "\n".join(lines)


class PartsReceiptImporter(AppService):
    """Читає CSV, перевіряє структуру, значення й дублікати, записує прихід.

    Наявний артикул: залишок збільшується, ціна оновлюється. Новий
    артикул: створюється картка запчастини. Повтор артикула у файлі:
    кількості додаються, діє ціна з останнього рядка. Рядки з помилками
    пропускаються; решта записується в одній транзакції.
    """

    def import_file(self, path: Path | str) -> ImportReport:
        report = ImportReport()
        records = self._read(Path(path))
        lines = self._parse(records, report)
        if not lines:
            if not report.errors:
                report.errors.append("У файлі немає рядків з даними")
            return report
        with self._unit() as uow:
            categories = {category.name.lower(): category
                          for category in uow.categories.all()}
            for line in lines:
                category = categories.get(line.category_name.lower())
                if category is None:
                    report.errors.append(
                        f"Рядок {line.line_number}: категорії "
                        f"«{line.category_name}» немає в довіднику")
                    continue
                self._apply(uow, line, category, report)
        report.errors.sort(key=_line_number)
        if report.imported:
            self._notify(Topic.STOCK, Topic.CATALOG)
        return report

    # ---- читання файлу ------------------------------------------------------

    def _read(self, path: Path) -> list[tuple[int, dict[str, str]]]:
        text = self._read_text(path)
        if not text.strip():
            raise ValidationError("Файл порожній", field="path")
        delimiter = self._detect_delimiter(text.splitlines()[0])
        reader = csv.reader(io.StringIO(text, newline=""),
                            delimiter=delimiter)
        header = next(reader)
        columns = [HEADER_ALIASES.get(name.strip().lower()) for name in header]
        missing = [FIELD_TITLES[name] for name in REQUIRED
                   if name not in columns]
        if missing:
            raise ValidationError(
                "У файлі немає обов'язкових стовпців: " + ", ".join(missing)
                + ". Перший рядок має містити заголовки: article; name; "
                "category; price; quantity (або українською).", field="path")
        records = []
        for line_number, values in enumerate(reader, start=2):
            if not any(value.strip() for value in values):
                continue
            if len(records) >= MAX_ROWS:
                raise ValidationError(
                    f"Файл завеликий: більше {MAX_ROWS} рядків", field="path")
            record = {column: value.strip()
                      for column, value in zip(columns, values) if column}
            records.append((line_number, record))
        return records

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise AutoServiceError(
                f"Не вдалося прочитати файл {path.name}: "
                f"{error.strerror or error}") from error
        # Excel у Windows часто зберігає CSV у cp1251, тому пробуємо обидва.
        for encoding in ("utf-8-sig", "cp1251"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValidationError("Не вдалося визначити кодування файлу; "
                              "збережіть його як CSV UTF-8", field="path")

    @staticmethod
    def _detect_delimiter(header_line: str) -> str:
        return max((";", ",", "\t"), key=header_line.count)

    # ---- перевірка рядків --------------------------------------------------

    def _parse(self, records, report: ImportReport) -> list[ReceiptLine]:
        by_article: dict[str, ReceiptLine] = {}
        for line_number, record in records:
            try:
                line = self._parse_record(line_number, record)
            except ValidationError as error:
                report.errors.append(f"Рядок {line_number}: {error.message}")
                continue
            previous = by_article.get(line.article)
            if previous is None:
                by_article[line.article] = line
                continue
            report.warnings.append(
                f"Рядок {line_number}: артикул {line.article} уже був у "
                f"рядку {previous.line_number}; кількості додано")
            previous.quantity += line.quantity
            previous.price = line.price
            if line.min_qty is not None:
                previous.min_qty = line.min_qty
        return list(by_article.values())

    @staticmethod
    def _parse_record(line_number: int, record: dict) -> ReceiptLine:
        article = normalize_article(record.get("article"))
        name = clean_text(record.get("name"), "name", "Назва", min_len=2,
                          max_len=120)
        category = clean_text(record.get("category"), "category",
                              "Категорія")
        price = Money.from_text(record.get("price", ""), field="price")
        quantity = check_int_range(record.get("quantity"), 1, 10_000,
                                   "quantity", "Кількість")
        min_text = record.get("min_qty", "")
        min_qty = (check_int_range(min_text, 0, 10_000, "min_qty",
                                   "Мінімальний залишок")
                   if min_text else None)
        return ReceiptLine(line_number, article, name, category, price,
                           quantity, min_qty)

    # ---- запис -------------------------------------------------------------

    @staticmethod
    def _apply(uow, line: ReceiptLine, category, report: ImportReport):
        part = uow.parts.find_by_article(line.article)
        if part is None:
            part = Part(category, line.article, line.name, line.price,
                        stock_qty=line.quantity, min_qty=line.min_qty or 0)
            uow.parts.insert(part)
            report.added += 1
            return
        part.receive(line.quantity)
        part.price = line.price
        if line.min_qty is not None:
            part.min_qty = line.min_qty
        uow.parts.update(part)
        uow.parts.update_stock(part)
        report.restocked += 1
