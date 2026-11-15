"""Політики знижок; замовлення працює з ними через спільний інтерфейс."""

from abc import ABC, abstractmethod

from models.order_lines import LineKind


class DiscountPolicy(ABC):
    """Скільки відсотків знижки діє на рядки певного виду."""

    @abstractmethod
    def percent_for(self, kind: LineKind) -> int:
        """Відсоток знижки для рядків виду `kind`."""

    @abstractmethod
    def describe(self) -> str:
        """Пояснення для підсумку замовлення."""


class NoDiscount(DiscountPolicy):
    def percent_for(self, kind: LineKind) -> int:
        return 0

    def describe(self) -> str:
        return "Без знижки"


class ManualDiscount(DiscountPolicy):
    """Знижка, яку майстер надав вручну; діє на роботи й запчастини."""

    def __init__(self, percent: int):
        self.percent = percent

    def percent_for(self, kind: LineKind) -> int:
        return self.percent

    def describe(self) -> str:
        return f"знижка майстра {self.percent} %"


class LoyaltyDiscount(DiscountPolicy):
    """Знижка постійного клієнта; діє лише на роботи, не на запчастини."""

    def __init__(self, percent: int):
        self.percent = percent

    def percent_for(self, kind: LineKind) -> int:
        return self.percent if kind is LineKind.WORK else 0

    def describe(self) -> str:
        return f"постійний клієнт {self.percent} % на роботи"


class BestOfDiscount(DiscountPolicy):
    """Кілька політик одночасно: для кожного виду рядків береться найбільша.

    Знижки не додаються: 10 % майстра й 5 % постійного клієнта дають 10 %.
    """

    def __init__(self, policies: list[DiscountPolicy]):
        self.policies = list(policies)

    def percent_for(self, kind: LineKind) -> int:
        return max((policy.percent_for(kind) for policy in self.policies),
                   default=0)

    def describe(self) -> str:
        parts = [policy.describe() for policy in self.policies
                 if any(policy.percent_for(kind) for kind in LineKind)]
        return "; ".join(parts) if parts else NoDiscount().describe()
