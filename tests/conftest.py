"""Спільні фікстури: тестові об'єкти моделей і бази."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from database import Database, SchemaManager, UnitOfWork
from database.demo_seeder import DemoSeeder
from models import (Car, Client, Employee, Money, Order, Part, RepairCategory,
                    WorkType)
from services import AppContext

FIXED_NOW = datetime(2026, 11, 14, 12, 0)


@pytest.fixture
def category():
    return RepairCategory("Гальмівна система", category_id=1)


@pytest.fixture
def client():
    return Client("Іваненко", "Петро", "067 123 45 67", client_id=1)


@pytest.fixture
def car(client):
    return Car(client, "Toyota", "Corolla", 2015, "AT1234BC",
               mileage_km=150_000, car_id=1)


@pytest.fixture
def mechanic(category):
    return Employee("Петрук", "Олег", "0501112233", date(2020, 1, 1),
                    category, employee_id=1)


@pytest.fixture
def brake_job(category):
    return WorkType(category, "Заміна колодок", Money.from_uah("450"), 0.8,
                    work_type_id=1)


@pytest.fixture
def brake_pads(category):
    return Part(category, "BRK-1", "Колодки передні", Money.from_uah("1250"),
                stock_qty=5, min_qty=2, part_id=1)


@pytest.fixture
def new_order(car, mechanic):
    return Order.open_new(car, mechanic, "Скрип гальм",
                          date.today() + timedelta(days=2), 151_000)


def make_database() -> Database:
    """Порожня база в пам'яті зі створеною схемою."""
    database = Database(":memory:")
    with UnitOfWork(database):
        SchemaManager().create(database.connection())
    return database


@pytest.fixture
def database():
    database = make_database()
    yield database
    database.close()


@pytest.fixture(scope="module")
def demo_database():
    """База з демо-даними, згенерованими на фіксовану дату."""
    database = Database(":memory:")
    with UnitOfWork(database) as uow:
        SchemaManager().create(database.connection())
        DemoSeeder(now=FIXED_NOW).seed(uow)
    yield database
    database.close()


@pytest.fixture
def app(database):
    """Усі сервіси на порожній базі з фіксованим «зараз»."""
    return AppContext(database, clock=lambda: FIXED_NOW)


@pytest.fixture
def shop(app):
    """Мінімальний автосервіс, створений через сервіси."""
    category = RepairCategory("Гальмівна система")
    app.catalog.save_category(category)
    client = Client("Іваненко", "Петро", "0671234567")
    app.customers.save_client(client)
    car = Car(client, "Toyota", "Corolla", 2015, "AT1234BC",
              mileage_km=150_000)
    app.customers.save_car(car)
    mechanic = Employee("Петрук", "Олег", "0501112233", date(2020, 1, 1),
                        category)
    app.staff.save(mechanic)
    work = WorkType(category, "Заміна колодок", Money.from_uah("450"), 0.8)
    app.catalog.save_work_type(work)
    part = Part(category, "BRK-1", "Колодки передні", Money.from_uah("1250"),
                stock_qty=5, min_qty=2)
    app.catalog.save_part(part)
    return SimpleNamespace(category=category, client=client, car=car,
                           mechanic=mechanic, work=work, part=part)


@pytest.fixture
def stored(database):
    """Мінімальний набір пов'язаних записів у базі."""
    with UnitOfWork(database) as uow:
        category = RepairCategory("Гальмівна система")
        uow.categories.insert(category)
        client = Client("Іваненко", "Петро", "0671234567")
        uow.clients.insert(client)
        car = Car(client, "Toyota", "Corolla", 2015, "AT1234BC",
                  mileage_km=150_000)
        uow.cars.insert(car)
        mechanic = Employee("Петрук", "Олег", "0501112233", date(2020, 1, 1),
                            category)
        uow.employees.insert(mechanic)
        work = WorkType(category, "Заміна колодок", Money.from_uah("450"), 0.8)
        uow.work_types.insert(work)
        part = Part(category, "BRK-1", "Колодки передні",
                    Money.from_uah("1250"), stock_qty=5, min_qty=2)
        uow.parts.insert(part)
    return {"category": category, "client": client, "car": car,
            "mechanic": mechanic, "work": work, "part": part}
