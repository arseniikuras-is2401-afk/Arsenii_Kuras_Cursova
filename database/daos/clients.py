"""Доступ до клієнтів і автомобілів."""

import sqlite3

from database.base_dao import TableDao
from database.query import SortKey
from models.car import Car
from models.person import Client
from models.validators import format_date


class ClientDao(TableDao):
    TABLE = "clients"
    PK = "client_id"
    LIST_SOURCE = "v_client_list"
    FIELDS = {
        "client_id": "client_id",
        "full_name": "full_name",
        "last_name": "last_name",
        "first_name": "first_name",
        "phone": "phone",
        "email": "coalesce(email, '')",
        "registered_on": "registered_on",
        "cars_count": "cars_count",
        "paid_orders": "paid_orders",
        "has_open_order": "has_open_order",
        "is_loyal": "is_loyal",
    }
    SEARCH_FIELDS = ("full_name", "phone", "email")
    DEFAULT_SORT = (SortKey("last_name"), SortKey("first_name"))
    USAGES = (("SELECT count(*) FROM cars WHERE client_id = ?",
               "автомобілів"),)
    NOT_FOUND = "Клієнта не знайдено; можливо, його вже видалено"

    def insert(self, client: Client) -> int:
        client.client_id = self._insert(self._values(client))
        return client.client_id

    def update(self, client: Client):
        self._update(client.client_id, self._values(client))

    def paid_orders_count(self, client_id: int) -> int:
        return self._connection.execute(
            "SELECT count(*) FROM orders o JOIN cars c ON c.car_id = o.car_id "
            "WHERE c.client_id = ? AND o.status = 'paid'",
            (client_id,)).fetchone()[0]

    def _values(self, client: Client) -> dict:
        return {
            "last_name": client.last_name,
            "first_name": client.first_name,
            "phone": client.phone,
            "email": client.email,
            "registered_on": format_date(client.registered_on),
            "note": client.note,
        }

    def _to_entity(self, row: sqlite3.Row) -> Client:
        return Client(row["last_name"], row["first_name"], row["phone"],
                      email=row["email"], registered_on=row["registered_on"],
                      note=row["note"], client_id=row["client_id"])


class CarDao(TableDao):
    TABLE = "cars"
    PK = "car_id"
    LIST_SOURCE = "v_car_list"
    FIELDS = {
        "car_id": "car_id",
        "client_id": "client_id",
        "plate_number": "plate_number",
        "vin": "coalesce(vin, '')",
        "make": "make",
        "model": "model",
        "production_year": "production_year",
        "mileage_km": "mileage_km",
        "owner_name": "owner_name",
        "owner_phone": "owner_phone",
        "orders_count": "orders_count",
        "last_visit": "coalesce(last_visit, '')",
        "has_open_order": "has_open_order",
    }
    SEARCH_FIELDS = ("plate_number", "vin", "make", "model", "owner_name")
    DEFAULT_SORT = (SortKey("plate_number"),)
    USAGES = (("SELECT count(*) FROM orders WHERE car_id = ?", "замовлень"),)
    NOT_FOUND = "Автомобіль не знайдено; можливо, його вже видалено"

    def __init__(self, connection: sqlite3.Connection, clients: ClientDao):
        super().__init__(connection)
        self._clients = clients

    def insert(self, car: Car) -> int:
        car.car_id = self._insert(self._values(car))
        return car.car_id

    def update(self, car: Car):
        self._update(car.car_id, self._values(car))

    def update_mileage(self, car: Car):
        self._update(car.car_id, {"mileage_km": car.mileage_km})

    def open_order_id(self, car_id: int) -> int | None:
        """Номер відкритого замовлення авто, якщо воно є."""
        row = self._connection.execute(
            "SELECT order_id FROM orders WHERE car_id = ? "
            "AND status IN ('new', 'in_progress')", (car_id,)).fetchone()
        return row[0] if row else None

    def makes(self) -> list[str]:
        """Наявні марки — для фільтра «Марка»."""
        return [row[0] for row in self._connection.execute(
            "SELECT DISTINCT make FROM cars ORDER BY make")]

    def _values(self, car: Car) -> dict:
        return {
            "client_id": car.owner.client_id,
            "make": car.make,
            "model": car.model,
            "production_year": car.production_year,
            "plate_number": car.plate_number,
            "vin": car.vin,
            "mileage_km": car.mileage_km,
        }

    def _to_entity(self, row: sqlite3.Row) -> Car:
        owner = self._clients.get(row["client_id"])
        return Car(owner, row["make"], row["model"], row["production_year"],
                   row["plate_number"], vin=row["vin"],
                   mileage_km=row["mileage_km"], car_id=row["car_id"])
