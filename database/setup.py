"""Відкриття бази під час запуску програми."""

from pathlib import Path

from database.connection import Database
from database.demo_seeder import DemoSeeder
from database.schema import SchemaManager
from database.unit_of_work import UnitOfWork


def open_database(path: Path | str, with_demo_data: bool = True) -> Database:
    """Відкриває базу; нову — створює й заповнює демо-даними.

    Схема й демо-дані записуються в одній транзакції: якщо заповнення
    перерветься, файл лишиться порожнім і наступний запуск почне спочатку.
    """
    database = Database(path)
    schema = SchemaManager()
    try:
        if schema.needs_creation(database.connection()):
            with UnitOfWork(database) as uow:
                schema.create(database.connection())
                if with_demo_data:
                    DemoSeeder().seed(uow)
    except Exception:
        database.close()
        raise
    return database
