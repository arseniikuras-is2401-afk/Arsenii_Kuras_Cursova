"""Довідники: категорії ремонту, прайс робіт і запчастини на складі."""

from config import (MAX_NORM_HOURS, MAX_PART_QUANTITY, MAX_PRICE_KOP,
                    MIN_NORM_HOURS)
from models.errors import InsufficientStockError, ValidationError
from models.money import Money
from models.validators import (check_int_range, clean_text,
                               normalize_article)


def _check_price(price: Money, field: str = "price") -> Money:
    if not isinstance(price, Money):
        raise TypeError("Ціна має бути об'єктом Money")
    if not 0 <= price.kop <= MAX_PRICE_KOP:
        raise ValidationError("Ціна має бути від 0 до 1 000 000 грн",
                              field=field)
    return price


class RepairCategory:
    """Вузол автомобіля / категорія ремонту: «Двигун», «Гальмівна система»."""

    def __init__(self, name: str, category_id: int | None = None):
        self.category_id = category_id
        self.name = name

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = clean_text(value, "name", "Назва категорії",
                                min_len=2, max_len=60)

    def __repr__(self) -> str:
        return f"RepairCategory({self.category_id}, {self.name!r})"


class WorkType:
    """Робота з прайсу: ціна за одиницю й нормо-години."""

    def __init__(self, category: RepairCategory, name: str, price: Money,
                 norm_hours: float, is_active: bool = True,
                 work_type_id: int | None = None):
        self.work_type_id = work_type_id
        self.category = category
        self.name = name
        self.price = price
        self.norm_hours = norm_hours
        self.is_active = bool(is_active)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = clean_text(value, "name", "Назва роботи",
                                min_len=3, max_len=120)

    @property
    def price(self) -> Money:
        return self._price

    @price.setter
    def price(self, value: Money):
        self._price = _check_price(value)

    @property
    def norm_hours(self) -> float:
        return self._norm_hours

    @norm_hours.setter
    def norm_hours(self, value: float):
        try:
            hours = round(float(value), 2)
        except (TypeError, ValueError) as error:
            raise ValidationError("Нормо-години мають бути числом",
                                  field="norm_hours") from error
        if not MIN_NORM_HOURS <= hours <= MAX_NORM_HOURS:
            raise ValidationError(
                f"Нормо-години мають бути від {MIN_NORM_HOURS:g} "
                f"до {MAX_NORM_HOURS:g}", field="norm_hours")
        self._norm_hours = hours


class Part:
    """Запчастина на складі.

    Залишок не має сетера: змінити його можна лише методами take(),
    put_back() і receive(), які не дають йому стати від'ємним.
    """

    def __init__(self, category: RepairCategory, article: str, name: str,
                 price: Money, stock_qty: int = 0, min_qty: int = 0,
                 part_id: int | None = None):
        self.part_id = part_id
        self.category = category
        self.article = article
        self.name = name
        self.price = price
        self._stock_qty = check_int_range(stock_qty, 0, 10**9, "stock_qty",
                                          "Залишок")
        self.min_qty = min_qty

    @property
    def article(self) -> str:
        return self._article

    @article.setter
    def article(self, value: str):
        self._article = normalize_article(value)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = clean_text(value, "name", "Назва запчастини",
                                min_len=2, max_len=120)

    @property
    def price(self) -> Money:
        return self._price

    @price.setter
    def price(self, value: Money):
        self._price = _check_price(value)

    @property
    def min_qty(self) -> int:
        return self._min_qty

    @min_qty.setter
    def min_qty(self, value: int):
        self._min_qty = check_int_range(value, 0, MAX_PART_QUANTITY,
                                        "min_qty", "Мінімальний залишок")

    @property
    def stock_qty(self) -> int:
        return self._stock_qty

    def is_low_stock(self) -> bool:
        return self._stock_qty < self._min_qty

    def take(self, quantity: int):
        """Списує запчастини зі складу для замовлення."""
        quantity = check_int_range(quantity, 1, MAX_PART_QUANTITY,
                                   "quantity", "Кількість")
        if quantity > self._stock_qty:
            raise InsufficientStockError(
                f"«{self.name}»: на складі лише {self._stock_qty} шт., "
                f"а потрібно {quantity}")
        self._stock_qty -= quantity

    def put_back(self, quantity: int):
        """Повертає раніше списані запчастини (скасування, видалення рядка)."""
        quantity = check_int_range(quantity, 1, MAX_PART_QUANTITY,
                                   "quantity", "Кількість")
        self._stock_qty += quantity

    def receive(self, quantity: int):
        """Прихід від постачальника."""
        quantity = check_int_range(quantity, 1, MAX_PART_QUANTITY,
                                   "quantity", "Кількість приходу")
        self._stock_qty += quantity

    def display_name(self) -> str:
        """«Колодки гальмівні передні [BRK-PAD-0451] · 8 шт.»"""
        return f"{self.name} [{self.article}] · {self._stock_qty} шт."
