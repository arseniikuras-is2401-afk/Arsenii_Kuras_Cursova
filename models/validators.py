"""Нормалізація та перевірка значень, спільні для моделей і форм."""

import re
from datetime import date, datetime

from config import DATE_FORMAT, DATETIME_FORMAT
from models.errors import ValidationError

_NAME_PATTERN = re.compile(r"^[A-Za-zА-ЩЬЮЯҐЄІЇа-щьюяґєії'’ʼ\- ]+$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_PLATE_PATTERN = re.compile(r"^[A-Z]{2}\d{4}[A-Z]{2}$")
# VIN: 17 символів, літери I, O, Q заборонені стандартом ISO 3779.
_VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_ARTICLE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-./]{1,29}$")

# Кириличні літери, що візуально збігаються з латинськими на номерних знаках.
_PLATE_LOOKALIKES = str.maketrans("АВЕІКМНОРСТХ", "ABEIKMHOPCTX")


def clean_text(value, field: str, label: str, min_len: int = 1,
               max_len: int = 200, required: bool = True) -> str | None:
    """Обрізає пробіли й перевіряє довжину.

    Порожнє необов'язкове поле → None.
    """
    text = " ".join(str(value or "").split())
    if not text:
        if required:
            raise ValidationError(f"Поле «{label}» обов'язкове", field=field)
        return None
    if not min_len <= len(text) <= max_len:
        raise ValidationError(
            f"Поле «{label}» має містити від {min_len} до {max_len} символів",
            field=field)
    return text


def normalize_name(value, field: str, label: str) -> str:
    """Прізвище або ім'я: 2–50 символів, лише літери, апостроф, дефіс."""
    text = clean_text(value, field, label, min_len=2, max_len=50)
    if not _NAME_PATTERN.match(text):
        raise ValidationError(
            f"Поле «{label}» може містити лише літери, апостроф і дефіс",
            field=field)
    return text[0].upper() + text[1:]


def normalize_phone(value, field: str = "phone") -> str:
    """Приводить номер до вигляду 0XXXXXXXXX; приймає +380, пробіли, дужки."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 12 and digits.startswith("380"):
        digits = "0" + digits[3:]
    if len(digits) != 10 or not digits.startswith("0"):
        raise ValidationError(
            "Номер має містити 10 цифр, наприклад 067 123 45 67", field=field)
    return digits


def format_phone(phone: str) -> str:
    """0671234567 → «067 123 45 67»."""
    if len(phone) != 10:
        return phone
    return f"{phone[:3]} {phone[3:6]} {phone[6:8]} {phone[8:]}"


def normalize_email(value, field: str = "email") -> str | None:
    """Порожній email → None (щоб UNIQUE не спрацьовував на порожніх)."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    if len(text) > 100 or not _EMAIL_PATTERN.match(text):
        raise ValidationError(
            "Email має формат ім'я@домен.зона, наприклад petro@ukr.net",
            field=field)
    return text


def normalize_plate(value, field: str = "plate_number") -> str:
    """Держномер у форматі AA1234BB латиницею у верхньому регістрі."""
    text = re.sub(r"[\s\-]", "", str(value or "")).upper()
    text = text.translate(_PLATE_LOOKALIKES)
    if not _PLATE_PATTERN.match(text):
        raise ValidationError(
            "Держномер має формат AA1234BB, наприклад AT1234BC", field=field)
    return text


def normalize_vin(value, field: str = "vin") -> str | None:
    """VIN необов'язковий; якщо вказаний — 17 символів без I, O, Q."""
    text = re.sub(r"\s", "", str(value or "")).upper()
    if not text:
        return None
    if not _VIN_PATTERN.match(text):
        raise ValidationError(
            "VIN має 17 символів (латинські літери й цифри) "
            "і не містить літер I, O, Q", field=field)
    return text


def normalize_article(value, field: str = "article") -> str:
    """Артикул запчастини: 2–30 символів A–Z, 0–9, «-», «.», «/»."""
    text = str(value or "").strip().upper()
    if not _ARTICLE_PATTERN.match(text):
        raise ValidationError(
            "Артикул: 2–30 латинських літер, цифр або символів - . /",
            field=field)
    return text


def check_int_range(value, low: int, high: int, field: str,
                    label: str) -> int:
    """Перевіряє, що значення — ціле число в межах [low, high]."""
    if isinstance(value, bool):
        raise ValidationError(f"Поле «{label}» має бути цілим числом",
                              field=field)
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"Поле «{label}» має бути цілим числом",
                              field=field) from error
    if number != value and not isinstance(value, str):
        raise ValidationError(f"Поле «{label}» має бути цілим числом",
                              field=field)
    if not low <= number <= high:
        raise ValidationError(
            f"Поле «{label}» має бути від {low} до {high}", field=field)
    return number


def parse_date(value, field: str = "date", label: str = "Дата") -> date:
    """Приймає date, «РРРР-ММ-ДД» або «ДД.ММ.РРРР»."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for pattern in (DATE_FORMAT, "%d.%m.%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValidationError(
        f"Поле «{label}»: дата має формат ДД.ММ.РРРР", field=field)


def parse_datetime(value) -> datetime:
    """Дата й час із бази (РРРР-ММ-ДД ГГ:ХХ) або вже готовий datetime."""
    if isinstance(value, datetime):
        return value
    return datetime.strptime(str(value), DATETIME_FORMAT)


def format_date(value: date | None) -> str | None:
    return value.strftime(DATE_FORMAT) if value else None


def format_datetime(value: datetime | None) -> str | None:
    return value.strftime(DATETIME_FORMAT) if value else None
