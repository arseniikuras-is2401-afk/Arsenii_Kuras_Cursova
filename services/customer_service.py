"""Клієнти та їхні автомобілі."""

import sqlite3

from database import Equals, ListQuery, SortKey
from models.car import Car
from models.errors import ValidationError
from models.person import Client
from services.base import AppService
from services.events import Topic

# Ім'я клієнта й держномер показуються в списках авто й замовлень, тому
# зміна клієнта чи авто оновлює й ці подання.
_CLIENT_TOPICS = (Topic.CLIENTS, Topic.CARS, Topic.ORDERS)
_CAR_TOPICS = (Topic.CARS, Topic.CLIENTS, Topic.ORDERS)


class CustomerService(AppService):
    """Облік клієнтів і їхніх авто."""

    # ---- клієнти ------------------------------------------------------------

    def find_clients(self, query: ListQuery | None = None) \
            -> list[sqlite3.Row]:
        with self._unit() as uow:
            return uow.clients.find(query)

    def get_client(self, client_id: int) -> Client:
        with self._unit() as uow:
            return uow.clients.get(client_id)

    def all_clients(self) -> list[Client]:
        """Усі клієнти за алфавітом — для списків вибору."""
        with self._unit() as uow:
            return [uow.clients.get(row["client_id"])
                    for row in uow.clients.find()]

    def save_client(self, client: Client) -> int:
        def checks(uow):
            self._ensure_unique(uow.clients, "phone", client.phone,
                                client.client_id,
                                "Клієнт з таким телефоном уже є в базі")
            self._ensure_unique(uow.clients, "email", client.email,
                                client.client_id,
                                "Клієнт з таким email уже є в базі")
        return self._run_save("clients", client, "client_id", checks,
                              _CLIENT_TOPICS)

    def delete_client(self, client_id: int):
        with self._unit() as uow:
            self._ensure_not_used(
                uow.clients, client_id, "Клієнта",
                "Спочатку видаліть його автомобілі без історії ремонтів.")
            uow.clients.delete(client_id)
        self._notify(*_CLIENT_TOPICS)

    # ---- автомобілі ---------------------------------------------------------

    def find_cars(self, query: ListQuery | None = None) -> list[sqlite3.Row]:
        with self._unit() as uow:
            return uow.cars.find(query)

    def get_car(self, car_id: int) -> Car:
        with self._unit() as uow:
            return uow.cars.get(car_id)

    def cars_of(self, client_id: int) -> list[Car]:
        """Авто клієнта — для форми нового замовлення."""
        query = ListQuery(criteria=[Equals("client_id", client_id)])
        with self._unit() as uow:
            return [uow.cars.get(row["car_id"])
                    for row in uow.cars.find(query)]

    def car_makes(self) -> list[str]:
        with self._unit() as uow:
            return uow.cars.makes()

    def save_car(self, car: Car) -> int:
        def checks(uow):
            uow.clients.get(car.owner.client_id)   # власник ще існує
            self._ensure_unique(uow.cars, "plate_number", car.plate_number,
                                car.car_id,
                                "Авто з таким держномером уже є в базі")
            self._ensure_unique(uow.cars, "vin", car.vin, car.car_id,
                                "Авто з таким VIN уже є в базі")
            if car.car_id is not None:
                stored = uow.cars.get(car.car_id)
                if car.mileage_km < stored.mileage_km:
                    raise ValidationError(
                        f"Пробіг не можна зменшити: останній відомий — "
                        f"{stored.mileage_km:,} км".replace(",", " "),
                        field="mileage_km")
        return self._run_save("cars", car, "car_id", checks, _CAR_TOPICS)

    def delete_car(self, car_id: int):
        with self._unit() as uow:
            self._ensure_not_used(uow.cars, car_id, "Автомобіль",
                                  "Історія ремонтів має зберігатися.")
            uow.cars.delete(car_id)
        self._notify(*_CAR_TOPICS)

    def car_history(self, car_id: int) -> list[sqlite3.Row]:
        """Усі замовлення авто, нові — першими."""
        query = ListQuery(criteria=[Equals("car_id", car_id)],
                          sort_keys=[SortKey("accepted_at", True)])
        with self._unit() as uow:
            return uow.orders.find(query)
