"""Сторінка «Замовлення»."""

from database.query import SortKey
from models.order import format_order_number
from models.order_state import OrderStatus
from services import Topic
from services.export import ColumnKind
from ui.filters import ChoiceFilter, FlagFilter, PeriodFilter
from ui.list_panel import ListPanel, make_button
from ui.pages.base import Page
from ui.table_model import ColumnSpec

COLUMNS = [
    ColumnSpec("order_number", "№", width=86, sort_field="order_id"),
    ColumnSpec("accepted_at", "Прийнято", ColumnKind.DATETIME, 122,
               "accepted_at"),
    ColumnSpec("plate_number", "Держномер", width=92,
               sort_field="plate_number"),
    ColumnSpec("car_title", "Авто", width=130, sort_field="car_title"),
    ColumnSpec("client_name", "Клієнт", width=150,
               sort_field="client_name", stretch=True),
    ColumnSpec("mechanic_name", "Механік", width=125,
               sort_field="mechanic_name"),
    ColumnSpec("due_date", "Термін", ColumnKind.DATE, 86, "due_date"),
    ColumnSpec("status", "Статус", ColumnKind.STATUS, 130, "status"),
    ColumnSpec("total_kop", "Сума, грн", ColumnKind.MONEY, 105, "total_kop"),
]

SORT_FIELDS = [("Дата приймання", "accepted_at"), ("Термін", "due_date"),
               ("Сума", "total_kop"), ("Клієнт", "client_name"),
               ("Механік", "mechanic_name"), ("Статус", "status"),
               ("Номер", "order_id")]


class OrdersPage(Page):
    TITLE = "Замовлення"
    SUBTITLE = "Наряди на ремонт: від приймання авто до оплати"
    TOPICS = frozenset({Topic.ORDERS, Topic.STAFF, Topic.CLIENTS,
                        Topic.CARS})

    def __init__(self, app, bridge, window):
        super().__init__(app, bridge, window)
        self.status_filter = ChoiceFilter(
            "Статус", "status",
            [(status.title, status.value) for status in OrderStatus])
        self.mechanic_filter = ChoiceFilter("Механік", "employee_id",
                                            width=170)
        self.overdue_filter = FlagFilter("Лише прострочені", "is_overdue")
        self.panel = ListPanel(
            COLUMNS, "order_id",
            "Пошук: номер, держномер, клієнт, телефон, модель",
            [self.status_filter, self.mechanic_filter,
             PeriodFilter("Прийнято", "accepted_on"), self.overdue_filter],
            SORT_FIELDS, SortKey("accepted_at", descending=True),
            tone=lambda row: "overdue" if row["is_overdue"] else None,
            empty_text="Замовлень ще немає")
        self.body.addWidget(self.panel)
        new = make_button("Нове замовлення", "plus", "primary",
                          "Ctrl+N")
        new.clicked.connect(lambda: window.new_order())
        self.header_actions.addWidget(new)
        self.open_button = make_button("Відкрити", "open")
        self.delete_button = make_button("Видалити", "trash", "danger")
        export = make_button("Експорт", "export")
        for button in (self.open_button, self.delete_button, export):
            self.panel.add_action(button)
        self.open_button.clicked.connect(self._open_selected)
        self.delete_button.clicked.connect(self._delete)
        export.clicked.connect(
            lambda: self.export(self.panel, "orders", "zamovlennia"))
        self.panel.query_changed.connect(self.refresh)
        self.panel.activated.connect(window.open_order)
        self.panel.delete_requested.connect(self._delete)
        self.panel.selection_changed.connect(self._update_buttons)

    def refresh(self):
        self.mechanic_filter.set_options(
            [(row["full_name"], row["employee_id"])
             for row in self._app.staff.find()])
        self.load(self.panel, self._app.orders.find)

    def show_overdue(self):
        """Перехід із головної сторінки: лише прострочені замовлення."""
        self.panel.filter_bar.reset()
        self.overdue_filter.set_checked(True)

    def _update_buttons(self, order_id):
        row = self.panel.selected_row()
        self.open_button.setEnabled(row is not None)
        can_delete = row is not None and OrderStatus(
            row["status"]).state.can_delete
        self.delete_button.setEnabled(can_delete)
        self.delete_button.setToolTip(
            "" if can_delete or row is None else
            "Видалити можна лише нове або скасоване замовлення")

    def _open_selected(self):
        order_id = self.panel.selected_id()
        if order_id is not None:
            self._window.open_order(order_id)

    def _delete(self):
        row = self.panel.selected_row()
        if row is None or not OrderStatus(row["status"]).state.can_delete:
            return
        note = ("Запчастини з нового замовлення повернуться на склад."
                if row["status"] == OrderStatus.NEW.value else "")
        self.delete_record(
            "замовлення", format_order_number(row["order_id"]),
            lambda: self._app.orders.delete(row["order_id"]), note)
