"""Головна сторінка: показники дня, прострочені замовлення, дефіцит."""

from datetime import date

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QVBoxLayout)

from services import Topic
from services.export import ColumnKind
from ui import formatting
from ui.list_panel import DataTable, make_button, make_card
from ui.pages.base import Page
from ui.table_model import ColumnSpec, RecordTableModel

OVERDUE_COLUMNS = [
    ColumnSpec("order_number", "№", width=92),
    ColumnSpec("plate_number", "Авто", width=95),
    ColumnSpec("client_name", "Клієнт", width=150, stretch=True),
    ColumnSpec("mechanic_name", "Механік", width=140),
    ColumnSpec("due_date", "Термін був", ColumnKind.DATE, 100),
]
LOW_COLUMNS = [
    ColumnSpec("name", "Запчастина", width=210, stretch=True),
    ColumnSpec("article", "Артикул", width=120),
    ColumnSpec("stock_qty", "Є", ColumnKind.INTEGER, 50),
    ColumnSpec("min_qty", "Мін.", ColumnKind.INTEGER, 50),
]


class MetricCard(QFrame):
    """Картка показника; клік переводить до відповідного списку."""

    clicked = pyqtSignal()

    def __init__(self, caption: str, hint: str = ""):
        super().__init__()
        self.setObjectName("MetricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(2)
        self.caption = QLabel(caption)
        self.caption.setObjectName("MetricCaption")
        self.value = QLabel("—")
        self.value.setObjectName("MetricValue")
        self.hint = QLabel(hint)
        self.hint.setObjectName("MetricCaption")
        layout.addWidget(self.caption)
        layout.addWidget(self.value)
        layout.addWidget(self.hint)

    def set_value(self, text: str, hint: str | None = None,
                  alert: bool = False):
        self.value.setText(text)
        if hint is not None:
            self.hint.setText(hint)
        self.setProperty("alert", alert)
        self.style().unpolish(self)
        self.style().polish(self)
        for child in (self.caption, self.value, self.hint):
            child.style().unpolish(child)
            child.style().polish(child)

    def make_clickable(self, tooltip: str):
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class DashboardPage(Page):
    TITLE = "Головна"
    TOPICS = frozenset({Topic.ORDERS, Topic.STOCK, Topic.CATALOG})

    def __init__(self, app, bridge, window):
        self.SUBTITLE = f"Сьогодні {formatting.long_date(date.today())}"
        super().__init__(app, bridge, window)
        new = make_button("Нове замовлення", "plus", "primary", "Ctrl+N")
        new.clicked.connect(lambda: window.new_order())
        self.header_actions.addWidget(new)
        self.cards = {
            "open": MetricCard("Відкриті замовлення"),
            "overdue": MetricCard("Прострочені"),
            "awaiting": MetricCard("Чекають оплати",
                                   "виконані, ще не оплачені"),
            "revenue": MetricCard("Виручка за місяць"),
            "check": MetricCard("Середній чек", "за поточний місяць"),
            "low": MetricCard("Мало на складі", "нижче мінімального залишку"),
        }
        grid = QGridLayout()
        grid.setSpacing(12)
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 3, index % 3)
        self.body.addLayout(grid)
        self._link(self.cards["open"], "Показати відкриті замовлення",
                   lambda: window.show_page("orders"))
        self._link(self.cards["overdue"], "Показати прострочені замовлення",
                   window.show_overdue_orders)
        self._link(self.cards["low"], "Показати дефіцитні запчастини",
                   window.show_low_stock)
        lists = QHBoxLayout()
        lists.setSpacing(12)
        self.overdue_model = RecordTableModel(OVERDUE_COLUMNS, "order_id")
        self.low_model = RecordTableModel(
            LOW_COLUMNS, "part_id", tone=lambda row: "low")
        overdue_card, overdue_table, self.overdue_empty = self._list_card(
            "Прострочені замовлення", self.overdue_model,
            "Прострочених замовлень немає")
        overdue_table.doubleClicked.connect(lambda index: window.open_order(
            self.overdue_model.id_at(index.row())))
        low_card, _, self.low_empty = self._list_card(
            "Мало на складі", self.low_model,
            "Усі запчастини вище мінімального залишку")
        lists.addWidget(overdue_card, 3)
        lists.addWidget(low_card, 2)
        self.body.addLayout(lists, 1)

    @staticmethod
    def _link(card: MetricCard, tooltip: str, action):
        card.make_clickable(tooltip)
        card.clicked.connect(action)

    def _list_card(self, title: str, model: RecordTableModel,
                   empty_text: str):
        card = make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        label = QLabel(title)
        label.setProperty("role", "sectionTitle")
        table = DataTable(model)
        empty = QLabel(empty_text)
        empty.setProperty("role", "muted")
        empty.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        layout.addWidget(table, 1)
        layout.addWidget(empty, 1)
        return card, table, empty

    def refresh(self):
        summary = self._app.reports.dashboard()
        cards = self.cards
        cards["open"].set_value(
            str(summary.open_orders), f"з них у роботі: {summary.in_progress}")
        cards["overdue"].set_value(
            str(summary.overdue),
            "минув плановий термін" if summary.overdue else "усе вчасно",
            alert=summary.overdue > 0)
        cards["awaiting"].set_value(str(summary.awaiting_payment))
        cards["revenue"].set_value(
            formatting.money_full(summary.revenue_month),
            formatting.plural(summary.paid_month, "оплачене замовлення",
                              "оплачені замовлення", "оплачених замовлень"))
        cards["check"].set_value(formatting.money_full(summary.average_check))
        cards["low"].set_value(str(summary.low_stock),
                               alert=summary.low_stock > 0)
        self.overdue_model.set_rows(summary.overdue_orders)
        self.low_model.set_rows(summary.low_stock_parts)
        self._toggle_empty(self.overdue_model, self.overdue_empty)
        self._toggle_empty(self.low_model, self.low_empty)

    @staticmethod
    def _toggle_empty(model: RecordTableModel, empty: QLabel):
        has_rows = bool(model.rows())
        empty.setVisible(not has_rows)
        empty.parentWidget().findChild(DataTable).setVisible(has_rows)
