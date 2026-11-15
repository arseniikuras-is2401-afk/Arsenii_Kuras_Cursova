"""Люди предметної області: клієнти й механіки."""

from abc import ABC, abstractmethod
from datetime import date

from models.catalog import RepairCategory
from models.errors import ValidationError
from models.validators import (clean_text, format_phone, normalize_email,
                               normalize_name, normalize_phone, parse_date)


class Person(ABC):
    """Спільні для клієнта й механіка ПІБ і телефон з перевіркою."""

    def __init__(self, last_name: str, first_name: str, phone: str):
        self.last_name = last_name
        self.first_name = first_name
        self.phone = phone

    @property
    def last_name(self) -> str:
        return self._last_name

    @last_name.setter
    def last_name(self, value: str):
        self._last_name = normalize_name(value, "last_name", "Прізвище")

    @property
    def first_name(self) -> str:
        return self._first_name

    @first_name.setter
    def first_name(self, value: str):
        self._first_name = normalize_name(value, "first_name", "Ім'я")

    @property
    def phone(self) -> str:
        """Телефон у вигляді 0XXXXXXXXX."""
        return self._phone

    @phone.setter
    def phone(self, value: str):
        self._phone = normalize_phone(value)

    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}"

    def short_name(self) -> str:
        """«Іваненко П.» — для вузьких стовпців таблиць."""
        return f"{self.last_name} {self.first_name[0]}."

    @abstractmethod
    def display_name(self) -> str:
        """Підпис у списках вибору; різний для клієнта й механіка."""


class Client(Person):
    """Клієнт автосервісу."""

    def __init__(self, last_name: str, first_name: str, phone: str,
                 email: str | None = None, registered_on: date | None = None,
                 note: str | None = None, client_id: int | None = None):
        super().__init__(last_name, first_name, phone)
        self.client_id = client_id
        self.email = email
        self.registered_on = registered_on or date.today()
        self.note = note

    @property
    def email(self) -> str | None:
        return self._email

    @email.setter
    def email(self, value: str | None):
        self._email = normalize_email(value)

    @property
    def registered_on(self) -> date:
        return self._registered_on

    @registered_on.setter
    def registered_on(self, value):
        self._registered_on = parse_date(value, "registered_on",
                                         "Дата реєстрації")

    @property
    def note(self) -> str | None:
        return self._note

    @note.setter
    def note(self, value: str | None):
        self._note = clean_text(value, "note", "Примітка", max_len=500,
                                required=False)

    def display_name(self) -> str:
        """«Іваненко Петро · 067 123 45 67».

        Телефон розрізняє однофамільців у списках вибору.
        """
        return f"{self.full_name()} · {format_phone(self.phone)}"


class Employee(Person):
    """Механік автосервісу."""

    def __init__(self, last_name: str, first_name: str, phone: str,
                 hired_on: date | None = None,
                 specialization: RepairCategory | None = None,
                 is_active: bool = True, employee_id: int | None = None):
        super().__init__(last_name, first_name, phone)
        self.employee_id = employee_id
        self.hired_on = hired_on or date.today()
        self.specialization = specialization
        self.is_active = bool(is_active)

    @property
    def hired_on(self) -> date:
        return self._hired_on

    @hired_on.setter
    def hired_on(self, value):
        hired = parse_date(value, "hired_on", "Дата прийому")
        if hired > date.today():
            raise ValidationError("Дата прийому не може бути в майбутньому",
                                  field="hired_on")
        self._hired_on = hired

    def display_name(self) -> str:
        """«Петрук Олег (Двигун)»; неактивного механіка позначено."""
        text = self.full_name()
        if self.specialization:
            text += f" ({self.specialization.name})"
        if not self.is_active:
            text += " — неактивний"
        return text
