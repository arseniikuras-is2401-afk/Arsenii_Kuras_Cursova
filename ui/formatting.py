"""Перетворення значень з бази на текст для інтерфейсу."""

from datetime import date, datetime

from models.money import Money
from models.order_state import OrderStatus
from models.validators import format_phone

MONTHS_GENITIVE = ("січня", "лютого", "березня", "квітня", "травня",
                   "червня", "липня", "серпня", "вересня", "жовтня",
                   "листопада", "грудня")


def money(kop: int | None) -> str:
    """125050 → «1 250,50» (без «грн»: валюта вказана в заголовку)."""
    return "" if kop is None else Money(kop).to_text(with_currency=False)


def money_full(value: Money | int) -> str:
    """«1 250,50 грн»."""
    amount = value if isinstance(value, Money) else Money(value)
    return amount.to_text()


def date_text(value) -> str:
    """«2026-11-14» або date → «14.11.2026»."""
    if not value:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d.%m.%Y")
    text = str(value)
    return f"{text[8:10]}.{text[5:7]}.{text[:4]}"


def datetime_text(value) -> str:
    """«2026-11-14 09:30» → «14.11.2026 09:30»."""
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    text = str(value)
    return f"{date_text(text[:10])} {text[11:16]}".strip()


def long_date(value: date) -> str:
    """«14 листопада 2026»."""
    return f"{value.day} {MONTHS_GENITIVE[value.month - 1]} {value.year}"


def number(value, decimals: int = 1) -> str:
    """1.5 → «1,5»; 2.0 → «2»."""
    if value is None:
        return ""
    text = f"{float(value):.{decimals}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def integer(value) -> str:
    """154300 → «154 300»."""
    return "" if value is None else f"{int(value):,}".replace(",", " ")


def phone(value) -> str:
    return format_phone(value) if value else ""


def status_title(value: str) -> str:
    return OrderStatus(value).title


def plural(count: int, one: str, few: str, many: str) -> str:
    """Українська форма слова для числа: 1 запис, 2 записи, 5 записів."""
    tail = count % 100
    if 11 <= tail <= 14:
        word = many
    elif count % 10 == 1:
        word = one
    elif 2 <= count % 10 <= 4:
        word = few
    else:
        word = many
    return f"{count} {word}"
