"""Сторінка «Статистика»: показники й графіки за період."""

from datetime import date

from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import (QComboBox, QDateEdit, QGridLayout, QHBoxLayout,
                             QLabel, QScrollArea, QVBoxLayout, QWidget)

from services import Topic
from ui import formatting
from ui.charts import ChartCanvas
from ui.filters import set_invalid
from ui.forms import UKRAINIAN
from ui.list_panel import make_card
from ui.pages.base import Page
from ui.pages.dashboard import MetricCard

PERIODS = ("Останні 3 місяці", "Останні 6 місяців", "Останні 12 місяців",
           "Цей рік", "Свій період…")
CUSTOM = len(PERIODS) - 1


def _months_back(today: date, months: int) -> date:
    """Перше число місяця, що на `months - 1` місяців раніше поточного."""
    year, month = today.year, today.month - (months - 1)
    while month <= 0:
        year, month = year - 1, month + 12
    return date(year, month, 1)


class StatisticsPage(Page):
    TITLE = "Статистика"
    SUBTITLE = "Виручка, популярні роботи й завантаженість механіків"
    TOPICS = frozenset({Topic.ORDERS, Topic.STAFF, Topic.CATALOG})

    def __init__(self, app, bridge, window):
        super().__init__(app, bridge, window)
        self.body.addWidget(self._controls())
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.revenue_card = MetricCard("Виручка за період")
        self.orders_card = MetricCard("Оплачено замовлень")
        self.check_card = MetricCard("Середній чек")
        self.days_card = MetricCard("Середня тривалість ремонту",
                                    "від початку робіт до завершення")
        for card in (self.revenue_card, self.orders_card, self.check_card,
                     self.days_card):
            cards.addWidget(card)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(cards)
        self.revenue_chart = ChartCanvas(3.0)
        self.works_chart = ChartCanvas(3.4)
        self.load_chart = ChartCanvas(3.4)
        layout.addWidget(self._chart_card(self.revenue_chart))
        bottom = QGridLayout()
        bottom.setSpacing(12)
        bottom.addWidget(self._chart_card(self.works_chart), 0, 0)
        bottom.addWidget(self._chart_card(self.load_chart), 0, 1)
        layout.addLayout(bottom)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        content.setObjectName("PageRoot")
        self.body.addWidget(scroll, 1)

    def _controls(self):
        card = make_card()
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(8)
        self.period = QComboBox()
        self.period.addItems(PERIODS)
        self.period.setCurrentIndex(1)
        self.start = self._date_edit()
        self.end = self._date_edit()
        self.mechanic = QComboBox()
        self.mechanic.setMinimumWidth(190)
        caption = QLabel("Період")
        caption.setProperty("role", "muted")
        row.addWidget(caption)
        row.addWidget(self.period)
        row.addWidget(self.start)
        self._dash = QLabel("–")
        row.addWidget(self._dash)
        row.addWidget(self.end)
        row.addSpacing(16)
        caption = QLabel("Механік")
        caption.setProperty("role", "muted")
        row.addWidget(caption)
        row.addWidget(self.mechanic)
        row.addStretch()
        note = QLabel("Механік впливає на виручку й популярні роботи")
        note.setProperty("role", "hint")
        row.addWidget(note)
        self.period.currentIndexChanged.connect(self._on_period)
        self.start.dateChanged.connect(self.safe_refresh)
        self.end.dateChanged.connect(self.safe_refresh)
        self.mechanic.currentIndexChanged.connect(self.safe_refresh)
        self._on_period(self.period.currentIndex(), refresh=False)
        return card

    def _date_edit(self) -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd.MM.yyyy")
        edit.setLocale(UKRAINIAN)
        edit.setDate(QDate.currentDate())
        return edit

    @staticmethod
    def _chart_card(chart: ChartCanvas):
        card = make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(chart)
        return card

    def _on_period(self, index: int, refresh: bool = True):
        custom = index == CUSTOM
        for widget in (self.start, self._dash, self.end):
            widget.setVisible(custom)
        if refresh:
            self.safe_refresh()

    def _range(self) -> tuple[date, date] | None:
        today = date.today()
        index = self.period.currentIndex()
        if index == CUSTOM:
            start = self.start.date().toPyDate()
            end = self.end.date().toPyDate()
            valid = start <= end
            set_invalid(self.end, not valid,
                        "Кінець періоду раніше за початок")
            return (start, end) if valid else None
        if index == 3:
            return date(today.year, 1, 1), today
        months = (3, 6, 12)[index]
        return _months_back(today, months), today

    def refresh(self):
        self._fill_mechanics()
        period = self._range()
        if period is None:
            return
        start, end = period
        employee_id = self.mechanic.currentData()
        reports = self._app.reports
        revenue, paid = reports.revenue_summary(start, end, employee_id)
        self.revenue_card.set_value(formatting.money_full(revenue))
        self.orders_card.set_value(str(paid))
        average = revenue.kop // paid if paid else 0
        self.check_card.set_value(formatting.money_full(average))
        days = reports.average_repair_days(start, end)
        self.days_card.set_value(
            "—" if days is None else f"{formatting.number(days)} дн.")
        self.revenue_chart.plot_columns(
            reports.revenue_by_month(start, end, employee_id),
            "Виручка по місяцях (оплачені замовлення)", "грн")
        self.works_chart.plot_bars(
            reports.top_work_types(start, end, employee_id),
            "Топ-10 робіт", "кількість замовлень")
        self.load_chart.plot_bars(
            reports.mechanic_load(start, end),
            "Завантаженість механіків", "нормо-години")

    def _fill_mechanics(self):
        current = self.mechanic.currentData()
        self.mechanic.blockSignals(True)
        self.mechanic.clear()
        self.mechanic.addItem("Усі механіки", None)
        for row in self._app.staff.find():
            self.mechanic.addItem(row["full_name"], row["employee_id"])
        index = self.mechanic.findData(current) if current else 0
        self.mechanic.setCurrentIndex(max(index, 0))
        self.mechanic.blockSignals(False)
