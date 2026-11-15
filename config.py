"""Шляхи до файлів і константи правил предметної області «Автосервіс»."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "autoservice.db"
RESOURCES_DIR = BASE_DIR / "resources"

APP_TITLE = "Автосервіс"
APP_VERSION = "1.0"
AUTHOR_FULL = "Курас Арсеній Володимирович"
AUTHOR_SHORT = "Курас Арсеній"
COLLEGE = ("ВСП «Фаховий коледж електронних приладів "
           "ІФНТУНГ»")
DISCIPLINE = "Об'єктно-орієнтоване програмування"
PROJECT_TOPIC = ("Розробка програмного додатку для роботи з базою даних "
                 "предметної області «Автосервіс»")
PROJECT_YEAR = 2026

# Формати збереження дат у базі (ISO 8601, тож рядки коректно сортуються).
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M"

# Правила замовлень.
MAX_OPEN_ORDERS_PER_MECHANIC = 4
LOYALTY_MIN_PAID_ORDERS = 5
LOYALTY_DISCOUNT_PCT = 5
MAX_MANUAL_DISCOUNT_PCT = 30
MAX_DUE_DAYS = 60
MAX_WORK_QUANTITY = 100
MAX_PART_QUANTITY = 10_000

# Межі значень довідників.
MIN_PRODUCTION_YEAR = 1950
MAX_PRICE_KOP = 1_000_000 * 100  # 1 000 000 грн
MIN_NORM_HOURS = 0.1
MAX_NORM_HOURS = 100.0

# Зерно генератора демо-даних: на будь-якому комп'ютері
# виходить той самий набір.
DEMO_SEED = 2026
