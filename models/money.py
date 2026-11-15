"""Грошова сума в копійках без похибок дробових чисел."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from models.errors import ValidationError

_AMOUNT_PATTERN = re.compile(r"^-?\d+(\.\d{1,2})?$")


@dataclass(frozen=True, order=True)
class Money:
    """Незмінна сума в копійках.

    Ціни зберігаються цілими числами, бо у float 0.1 + 0.2 != 0.3, а сума
    замовлення має сходитися до копійки з тим, що рахує SQL-представлення.
    """

    kop: int = 0

    def __post_init__(self):
        if isinstance(self.kop, bool) or not isinstance(self.kop, int):
            raise TypeError("Сума зберігається цілою кількістю копійок")

    @classmethod
    def from_text(cls, text: str, field: str | None = None) -> "Money":
        """Розбирає введену суму: «1250», «1 250,5», «1250.50 грн»."""
        cleaned = (str(text).replace("грн", "").replace(" ", "")
                   .replace(" ", "").replace(",", "."))
        if not _AMOUNT_PATTERN.match(cleaned):
            raise ValidationError(
                "Введіть суму, наприклад 1250,50", field=field)
        return cls.from_uah(cleaned)

    @classmethod
    def from_uah(cls, value) -> "Money":
        """Створює суму з гривень (int, str або Decimal; float — через str)."""
        try:
            amount = Decimal(str(value))
        except InvalidOperation as error:
            raise ValidationError(f"Некоректна сума: {value}") from error
        return cls(int((amount * 100).to_integral_value()))

    def __add__(self, other: "Money") -> "Money":
        return Money(self.kop + other.kop)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self.kop - other.kop)

    def __mul__(self, quantity: int) -> "Money":
        return Money(self.kop * quantity)

    __rmul__ = __mul__

    def percent(self, pct: int) -> "Money":
        """Відсоток від суми з округленням половини копійки вгору.

        Формула (kop * pct + 50) // 100 збігається з v_order_list у базі.
        """
        sign = -1 if self.kop < 0 else 1
        return Money(sign * ((abs(self.kop) * pct + 50) // 100))

    def to_uah(self) -> Decimal:
        """Сума в гривнях з двома знаками після коми."""
        return Decimal(self.kop) / 100

    def to_text(self, with_currency: bool = True) -> str:
        """Форматує як «1 234,50 грн»."""
        sign = "−" if self.kop < 0 else ""
        hryvnias, kopecks = divmod(abs(self.kop), 100)
        grouped = f"{hryvnias:,}".replace(",", " ")
        text = f"{sign}{grouped},{kopecks:02d}"
        return f"{text} грн" if with_currency else text

    def is_zero(self) -> bool:
        return self.kop == 0

    def __str__(self) -> str:
        return self.to_text()


ZERO = Money(0)
