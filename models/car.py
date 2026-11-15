"""Автомобіль клієнта."""

from datetime import date

from config import MIN_PRODUCTION_YEAR
from models.errors import ValidationError
from models.person import Client
from models.validators import (check_int_range, clean_text,
                               normalize_plate, normalize_vin)


class Car:
    """Автомобіль; власник входить до складу об'єкта."""

    def __init__(self, owner: Client, make: str, model: str,
                 production_year: int, plate_number: str,
                 vin: str | None = None, mileage_km: int = 0,
                 car_id: int | None = None):
        self.car_id = car_id
        self.owner = owner
        self.make = make
        self.model = model
        self.production_year = production_year
        self.plate_number = plate_number
        self.vin = vin
        self._mileage_km = check_int_range(mileage_km, 0, 5_000_000,
                                           "mileage_km", "Пробіг")

    @property
    def make(self) -> str:
        return self._make

    @make.setter
    def make(self, value: str):
        self._make = clean_text(value, "make", "Марка", min_len=2, max_len=40)

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str):
        self._model = clean_text(value, "model", "Модель", max_len=40)

    @property
    def production_year(self) -> int:
        return self._production_year

    @production_year.setter
    def production_year(self, value: int):
        self._production_year = check_int_range(
            value, MIN_PRODUCTION_YEAR, date.today().year + 1,
            "production_year", "Рік випуску")

    @property
    def plate_number(self) -> str:
        return self._plate_number

    @plate_number.setter
    def plate_number(self, value: str):
        self._plate_number = normalize_plate(value)

    @property
    def vin(self) -> str | None:
        return self._vin

    @vin.setter
    def vin(self, value: str | None):
        self._vin = normalize_vin(value)

    @property
    def mileage_km(self) -> int:
        """Останній відомий пробіг; змінює лише register_mileage()."""
        return self._mileage_km

    def register_mileage(self, km: int):
        """Записує новий пробіг; зменшити його не можна."""
        km = check_int_range(km, 0, 5_000_000, "intake_mileage_km", "Пробіг")
        if km < self._mileage_km:
            raise ValidationError(
                f"Пробіг не може бути меншим за {self._mileage_km:,} км "
                f"(останній відомий)".replace(",", " "),
                field="intake_mileage_km")
        self._mileage_km = km

    def title(self) -> str:
        """«AT1234BC — Toyota Corolla»."""
        return f"{self.plate_number} — {self.make} {self.model}"

    def display_name(self) -> str:
        return f"{self.title()} {self.production_year}"
