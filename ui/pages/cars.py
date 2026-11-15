"""Сторінка «Автомобілі» з історією ремонтів вибраного авто."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QSplitter, QVBoxLayout

from database.query import SortKey
from services import Topic
from services.export import ColumnKind
from ui.dialogs import CarForm
from ui.filters import ChoiceFilter, FlagFilter, NumberRangeFilter
from ui.list_panel import DataTable, ListPanel, make_button, make_card
from ui.messages import run_safely
from ui.pages.base import Page
from ui.table_model import ColumnSpec, RecordTableModel

COLUMNS = [
    ColumnSpec("plate_number", "Держномер", width=100,
               sort_field="plate_number"),
    ColumnSpec("make", "Марка", width=110, sort_field="make"),
    ColumnSpec("model", "Модель", width=100, sort_field="model"),
    ColumnSpec("production_year", "Рік", width=56,
               sort_field="production_year"),
    ColumnSpec("mileage_km", "Пробіг, км", ColumnKind.INTEGER, 100,
               "mileage_km"),
    ColumnSpec("owner_name", "Власник", width=170, sort_field="owner_name",
               stretch=True),
    ColumnSpec("owner_phone", "Телефон", ColumnKind.PHONE, 125),
    ColumnSpec("last_visit", "Останній візит", ColumnKind.DATE, 120,
               "last_visit"),
]

HISTORY_COLUMNS = [
    ColumnSpec("order_number", "№", width=92),
    ColumnSpec("accepted_at", "Прийнято", ColumnKind.DATE, 100),
    ColumnSpec("mechanic_name", "Механік", width=140),
    ColumnSpec("status", "Статус", ColumnKind.STATUS, 170),
    ColumnSpec("total_kop", "Сума, грн", ColumnKind.MONEY, 100),
    ColumnSpec("complaint", "Скарга", width=200, stretch=True),
]


class CarsPage(Page):
    TITLE = "Автомобілі"
    SUBTITLE = "Усі авто клієнтів та історія їхніх ремонтів"
    TOPICS = frozenset({Topic.CARS, Topic.CLIENTS, Topic.ORDERS})

    def __init__(self, app, bridge, window):
        super().__init__(app, bridge, window)
        self.make_filter = ChoiceFilter("Марка", "make", width=130)
        self.panel = ListPanel(
            COLUMNS, "car_id",
            "Пошук: держномер, VIN, марка, модель, власник",
            [self.make_filter,
             NumberRangeFilter("Рік випуску", "production_year",
                               decimals=0),
             FlagFilter("Є відкрите замовлення", "has_open_order")],
            [("Держномер", "plate_number"), ("Марка", "make"),
             ("Рік випуску", "production_year"), ("Пробіг", "mileage_km"),
             ("Останній візит", "last_visit"), ("Власник", "owner_name")],
            SortKey("plate_number"), empty_text="Автомобілів ще немає")
        add = make_button("Новий автомобіль", "plus", "primary")
        add.clicked.connect(
            lambda: CarForm(self._app, parent=self).exec_())
        self.header_actions.addWidget(add)
        self.edit_button = make_button("Редагувати", "edit")
        self.order_button = make_button("Нове замовлення", "orders")
        self.delete_button = make_button("Видалити", "trash", "danger")
        export = make_button("Експорт", "export")
        for button in (self.edit_button, self.order_button,
                       self.delete_button, export):
            self.panel.add_action(button)
        self.edit_button.clicked.connect(self._edit)
        self.order_button.clicked.connect(
            lambda: window.new_order(self.panel.selected_id()))
        self.delete_button.clicked.connect(self._delete)
        export.clicked.connect(
            lambda: self.export(self.panel, "cars", "avtomobili"))
        self.panel.query_changed.connect(self.refresh)
        self.panel.activated.connect(lambda _: self._edit())
        self.panel.delete_requested.connect(self._delete)
        self.panel.selection_changed.connect(self._on_selected)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.panel)
        splitter.addWidget(self._history_card())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.body.addWidget(splitter)

    def _history_card(self):
        card = make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        self.history_title = QLabel("Історія ремонтів")
        self.history_title.setProperty("role", "sectionTitle")
        hint = QLabel("Подвійне клацання відкриває замовлення")
        hint.setProperty("role", "hint")
        self.history_model = RecordTableModel(
            HISTORY_COLUMNS, "order_id",
            tone=lambda row: "overdue" if row["is_overdue"] else None)
        table = DataTable(self.history_model)
        table.doubleClicked.connect(lambda index: self._window.open_order(
            self.history_model.id_at(index.row())))
        layout.addWidget(self.history_title)
        layout.addWidget(hint)
        layout.addWidget(table)
        card.setMinimumHeight(190)
        return card

    def refresh(self):
        self.make_filter.set_options(
            [(make, make) for make in self._app.customers.car_makes()])
        self.load(self.panel, self._app.customers.find_cars)

    def _on_selected(self, car_id):
        has = car_id is not None
        for button in (self.edit_button, self.order_button,
                       self.delete_button):
            button.setEnabled(has)
        row = self.panel.selected_row()
        if row is None:
            self.history_title.setText("Історія ремонтів")
            self.history_model.set_rows([])
            return
        history = self._app.customers.car_history(car_id)
        self.history_title.setText(
            f"Історія ремонтів {row['plate_number']} ({len(history)})")
        self.history_model.set_rows(history)

    def _edit(self):
        car_id = self.panel.selected_id()
        if car_id is None:
            return
        car = run_safely(self, lambda: self._app.customers.get_car(car_id))
        if car:
            CarForm(self._app, car, parent=self).exec_()

    def _delete(self):
        row = self.panel.selected_row()
        if row:
            self.delete_record(
                "автомобіль", row["plate_number"],
                lambda: self._app.customers.delete_car(row["car_id"]))
