"""Сторінка «Клієнти» з автомобілями вибраного клієнта."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSplitter, QVBoxLayout

from database.query import Equals, ListQuery, SortKey
from services import Topic
from services.export import ColumnKind
from ui.dialogs import CarForm, ClientForm
from ui.filters import FlagFilter, PeriodFilter
from ui.list_panel import DataTable, ListPanel, make_button, make_card
from ui.messages import run_safely
from ui.pages.base import Page
from ui.table_model import ColumnSpec, RecordTableModel

COLUMNS = [
    ColumnSpec("full_name", "Клієнт", width=200, sort_field="full_name"),
    ColumnSpec("phone", "Телефон", ColumnKind.PHONE, 130, "phone"),
    ColumnSpec("email", "Email", width=200, sort_field="email",
               stretch=True),
    ColumnSpec("cars_count", "Авто", ColumnKind.INTEGER, 60, "cars_count"),
    ColumnSpec("paid_orders", "Оплачено замовлень", ColumnKind.INTEGER, 140,
               "paid_orders"),
    ColumnSpec("is_loyal", "Постійний", ColumnKind.BOOLEAN, 90, "is_loyal"),
    ColumnSpec("registered_on", "Зареєстровано", ColumnKind.DATE, 120,
               "registered_on"),
]

CAR_COLUMNS = [
    ColumnSpec("plate_number", "Держномер", width=100),
    ColumnSpec("make", "Марка", width=120),
    ColumnSpec("model", "Модель", width=120, stretch=True),
    ColumnSpec("production_year", "Рік", width=60),
    ColumnSpec("mileage_km", "Пробіг, км", ColumnKind.INTEGER, 100),
    ColumnSpec("orders_count", "Замовлень", ColumnKind.INTEGER, 90),
    ColumnSpec("has_open_order", "Є відкрите", ColumnKind.BOOLEAN, 90),
]


class ClientsPage(Page):
    TITLE = "Клієнти"
    SUBTITLE = "Контакти клієнтів і їхні автомобілі"
    TOPICS = frozenset({Topic.CLIENTS, Topic.CARS, Topic.ORDERS})

    def __init__(self, app, bridge, window):
        super().__init__(app, bridge, window)
        self.panel = ListPanel(
            COLUMNS, "client_id", "Пошук: прізвище, ім'я, телефон, email",
            [PeriodFilter("Реєстрація", "registered_on"),
             FlagFilter("Є відкрите замовлення", "has_open_order"),
             FlagFilter("Лише постійні клієнти", "is_loyal")],
            [("Прізвище та ім'я", "full_name"),
             ("Дата реєстрації", "registered_on"),
             ("Оплачено замовлень", "paid_orders"),
             ("Кількість авто", "cars_count")],
            SortKey("full_name"), empty_text="Клієнтів ще немає")
        add = make_button("Новий клієнт", "plus", "primary")
        add.clicked.connect(self._add)
        self.header_actions.addWidget(add)
        self.edit_button = make_button("Редагувати", "edit")
        self.delete_button = make_button("Видалити", "trash", "danger")
        export = make_button("Експорт", "export")
        for button in (self.edit_button, self.delete_button, export):
            self.panel.add_action(button)
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)
        export.clicked.connect(
            lambda: self.export(self.panel, "clients", "kliienty"))
        self.panel.query_changed.connect(self.refresh)
        self.panel.activated.connect(lambda _: self._edit())
        self.panel.delete_requested.connect(self._delete)
        self.panel.selection_changed.connect(self._on_client_selected)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.panel)
        splitter.addWidget(self._cars_card())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.body.addWidget(splitter)

    def _cars_card(self):
        card = make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        self.cars_title = QLabel("Автомобілі клієнта")
        self.cars_title.setProperty("role", "sectionTitle")
        layout.addWidget(self.cars_title)
        self.cars_model = RecordTableModel(CAR_COLUMNS, "car_id")
        self.cars_table = DataTable(self.cars_model)
        self.cars_table.setMinimumHeight(130)
        layout.addWidget(self.cars_table)
        buttons = QHBoxLayout()
        self.add_car = make_button("Додати авто", "plus")
        self.edit_car = make_button("Редагувати авто", "edit")
        self.order_car = make_button("Нове замовлення", "orders")
        self.delete_car = make_button("Видалити авто", "trash", "danger")
        for button in (self.add_car, self.edit_car, self.order_car):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(self.delete_car)
        layout.addLayout(buttons)
        self.add_car.clicked.connect(self._add_car)
        self.edit_car.clicked.connect(self._edit_car)
        self.order_car.clicked.connect(
            lambda: self._window.new_order(self._selected_car()))
        self.delete_car.clicked.connect(self._delete_car)
        self.cars_table.doubleClicked.connect(lambda _: self._edit_car())
        self.cars_table.selectionModel().selectionChanged.connect(
            lambda *_: self._update_car_buttons())
        return card

    # ---- дані ---------------------------------------------------------------

    def refresh(self):
        self.load(self.panel, self._app.customers.find_clients)
        self._load_cars()

    def _on_client_selected(self, client_id):
        has = client_id is not None
        self.edit_button.setEnabled(has)
        self.delete_button.setEnabled(has)
        self._load_cars()

    def _load_cars(self):
        row = self.panel.selected_row()
        if row is None:
            self.cars_title.setText("Автомобілі клієнта")
            self.cars_model.set_rows([])
        else:
            self.cars_title.setText(f"Автомобілі: {row['full_name']}")
            query = ListQuery(criteria=[Equals("client_id",
                                               row["client_id"])])
            self.cars_model.set_rows(self._app.customers.find_cars(query))
        self.add_car.setEnabled(row is not None)
        self._update_car_buttons()

    def _selected_car(self) -> int | None:
        rows = self.cars_table.selectionModel().selectedRows()
        return self.cars_model.id_at(rows[0].row()) if rows else None

    def _update_car_buttons(self):
        has = self._selected_car() is not None
        for button in (self.edit_car, self.order_car, self.delete_car):
            button.setEnabled(has)

    # ---- дії ---------------------------------------------------------------

    def _add(self):
        form = ClientForm(self._app, parent=self)
        if form.exec_() and form.saved_id:
            self.panel.select_id(form.saved_id)

    def _edit(self):
        client_id = self.panel.selected_id()
        if client_id is None:
            return
        client = run_safely(self, lambda: self._app.customers.get_client(
            client_id))
        if client:
            ClientForm(self._app, client, self).exec_()

    def _delete(self):
        row = self.panel.selected_row()
        if row:
            self.delete_record(
                "клієнта", row["full_name"],
                lambda: self._app.customers.delete_client(row["client_id"]))

    def _add_car(self):
        client_id = self.panel.selected_id()
        if client_id is not None:
            CarForm(self._app, owner_id=client_id, parent=self).exec_()

    def _edit_car(self):
        car_id = self._selected_car()
        if car_id is None:
            return
        car = run_safely(self, lambda: self._app.customers.get_car(car_id))
        if car:
            CarForm(self._app, car, parent=self).exec_()

    def _delete_car(self):
        car_id = self._selected_car()
        if car_id is None:
            return
        row = self.cars_model.row_data(self.cars_model.row_of(car_id))
        self.delete_record(
            "автомобіль", row["plate_number"],
            lambda: self._app.customers.delete_car(car_id))
