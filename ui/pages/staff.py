"""Сторінка «Механіки»."""

from database.query import SortKey
from services import Topic
from services.export import ColumnKind
from ui.dialogs import EmployeeForm
from ui.filters import ChoiceFilter, FlagFilter
from ui.list_panel import ListPanel, make_button
from ui.messages import run_safely
from ui.pages.base import Page
from ui.table_model import ColumnSpec

COLUMNS = [
    ColumnSpec("full_name", "Механік", width=190, sort_field="full_name"),
    ColumnSpec("phone", "Телефон", ColumnKind.PHONE, 130, "phone"),
    ColumnSpec("category_name", "Спеціалізація", width=170,
               sort_field="category_name", stretch=True),
    ColumnSpec("hired_on", "Прийнято на роботу", ColumnKind.DATE, 150,
               "hired_on"),
    ColumnSpec("open_orders", "Відкриті замовлення", ColumnKind.INTEGER,
               150, "open_orders"),
    ColumnSpec("total_orders", "Усього замовлень", ColumnKind.INTEGER, 130,
               "total_orders"),
    ColumnSpec("is_active", "Працює", ColumnKind.BOOLEAN, 80, "is_active"),
]


class StaffPage(Page):
    TITLE = "Механіки"
    SUBTITLE = "Персонал і поточне навантаження"
    TOPICS = frozenset({Topic.STAFF, Topic.ORDERS, Topic.CATALOG})

    def __init__(self, app, bridge, window):
        super().__init__(app, bridge, window)
        self.category_filter = ChoiceFilter("Спеціалізація", "category_id",
                                            width=170)
        self.panel = ListPanel(
            COLUMNS, "employee_id", "Пошук: прізвище, ім'я, телефон",
            [self.category_filter, FlagFilter("Лише працюючі", "is_active"),
             FlagFilter("Є відкриті замовлення", "open_orders")],
            [("Прізвище та ім'я", "full_name"),
             ("Відкриті замовлення", "open_orders"),
             ("Усього замовлень", "total_orders"),
             ("Дата прийому", "hired_on")],
            SortKey("full_name"),
            tone=lambda row: None if row["is_active"] else "inactive",
            empty_text="Механіків ще немає")
        add = make_button("Новий механік", "plus", "primary")
        add.clicked.connect(
            lambda: EmployeeForm(self._app, parent=self).exec_())
        self.header_actions.addWidget(add)
        self.edit_button = make_button("Редагувати", "edit")
        self.toggle_button = make_button("Деактивувати", "power")
        self.delete_button = make_button("Видалити", "trash", "danger")
        export = make_button("Експорт", "export")
        for button in (self.edit_button, self.toggle_button,
                       self.delete_button, export):
            self.panel.add_action(button)
        self.edit_button.clicked.connect(self._edit)
        self.toggle_button.clicked.connect(self._toggle)
        self.delete_button.clicked.connect(self._delete)
        export.clicked.connect(
            lambda: self.export(self.panel, "employees", "mekhaniky"))
        self.panel.query_changed.connect(self.refresh)
        self.panel.activated.connect(lambda _: self._edit())
        self.panel.delete_requested.connect(self._delete)
        self.panel.selection_changed.connect(self._update_buttons)
        self.body.addWidget(self.panel)

    def refresh(self):
        self.category_filter.set_options(
            [(category.name, category.category_id)
             for category in self._app.catalog.categories()])
        self.load(self.panel, self._app.staff.find)

    def _update_buttons(self, employee_id):
        row = self.panel.selected_row()
        for button in (self.edit_button, self.toggle_button,
                       self.delete_button):
            button.setEnabled(row is not None)
        if row is None:
            return
        active = bool(row["is_active"])
        self.toggle_button.setText("Деактивувати" if active
                                   else "Активувати")
        blocked = active and row["open_orders"] > 0
        self.toggle_button.setEnabled(not blocked)
        self.toggle_button.setToolTip(
            "Спершу передайте відкриті замовлення іншому механіку"
            if blocked else "")

    def _edit(self):
        employee_id = self.panel.selected_id()
        if employee_id is None:
            return
        employee = run_safely(self, lambda: self._app.staff.get(employee_id))
        if employee:
            EmployeeForm(self._app, employee, self).exec_()

    def _toggle(self):
        row = self.panel.selected_row()
        if row is None:
            return
        active = not row["is_active"]
        run_safely(self, lambda: self._app.staff.set_active(
            row["employee_id"], active),
            f"{row['full_name']}: " + ("активовано" if active
                                       else "деактивовано"))

    def _delete(self):
        row = self.panel.selected_row()
        if row:
            self.delete_record(
                "механіка", row["full_name"],
                lambda: self._app.staff.delete(row["employee_id"]))
