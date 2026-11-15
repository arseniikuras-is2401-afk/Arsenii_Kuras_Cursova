"""Підсумкові показники для головної сторінки й графіків."""

import sqlite3
from dataclasses import dataclass
from datetime import date

from models.errors import ValidationError
from models.money import Money
from services.base import AppService

MONTH_NAMES = ("січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер",
               "вер", "жов", "лис", "гру")


@dataclass(frozen=True)
class DashboardSummary:
    """Показники головної сторінки."""

    open_orders: int
    in_progress: int
    overdue: int
    awaiting_payment: int
    revenue_month: Money
    paid_month: int
    average_check: Money
    low_stock: int
    overdue_orders: list[sqlite3.Row]
    low_stock_parts: list[sqlite3.Row]


@dataclass(frozen=True)
class ChartPoint:
    """Одна точка графіка: підпис і значення."""

    label: str
    value: float


class ReportService(AppService):
    """Читає агрегати з бази й готує їх для інтерфейсу."""

    def dashboard(self) -> DashboardSummary:
        today = self._today()
        with self._unit() as uow:
            data = uow.reports.dashboard(today)
            overdue = uow.reports.overdue_orders(today)
            low = uow.reports.low_stock_parts()
        return DashboardSummary(
            open_orders=data["open_orders"],
            in_progress=data["in_progress"],
            overdue=data["overdue"],
            awaiting_payment=data["awaiting_payment"],
            revenue_month=Money(data["revenue_month_kop"]),
            paid_month=data["paid_month"],
            average_check=Money(data["average_check_kop"]),
            low_stock=data["low_stock"],
            overdue_orders=overdue,
            low_stock_parts=low)

    def revenue_by_month(self, start: date, end: date,
                         employee_id: int | None = None) -> list[ChartPoint]:
        """Виручка в гривнях по місяцях; місяці без оплат — нулі."""
        self._check_period(start, end)
        with self._unit() as uow:
            rows = uow.reports.revenue_by_month(start, end, employee_id)
        by_month = {row["month"]: row["revenue_kop"] for row in rows}
        return [ChartPoint(label, by_month.get(key, 0) / 100)
                for key, label in _months_between(start, end)]

    def revenue_summary(self, start: date, end: date,
                        employee_id: int | None = None) \
            -> tuple[Money, int]:
        """Виручка й кількість оплачених замовлень за період."""
        self._check_period(start, end)
        with self._unit() as uow:
            rows = uow.reports.revenue_by_month(start, end, employee_id)
        return (Money(sum(row["revenue_kop"] for row in rows)),
                sum(row["orders"] for row in rows))

    def top_work_types(self, start: date, end: date,
                       employee_id: int | None = None,
                       limit: int = 10) -> list[ChartPoint]:
        """Найчастіші роботи: у скількох замовленнях за період."""
        self._check_period(start, end)
        with self._unit() as uow:
            rows = uow.reports.top_work_types(start, end, limit, employee_id)
        return [ChartPoint(row["name"], row["orders"]) for row in rows]

    def mechanic_load(self, start: date, end: date) -> list[ChartPoint]:
        """Нормо-години механіків за період."""
        self._check_period(start, end)
        with self._unit() as uow:
            rows = uow.reports.mechanic_load(start, end)
        return [ChartPoint(row["mechanic_name"], row["labor_hours"])
                for row in rows]

    def average_repair_days(self, start: date, end: date) -> float | None:
        self._check_period(start, end)
        with self._unit() as uow:
            return uow.reports.average_repair_days(start, end)

    @staticmethod
    def _check_period(start: date, end: date):
        if start > end:
            raise ValidationError(
                "Початок періоду не може бути пізніше за кінець",
                field="period")


def _months_between(start: date, end: date) -> list[tuple[str, str]]:
    """[('2026-09', 'вер 2026'), ...] від місяця start до місяця end."""
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((f"{year}-{month:02d}",
                       f"{MONTH_NAMES[month - 1]} {year}"))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months
