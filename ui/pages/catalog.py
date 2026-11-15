"""Сторінка «Прайс робіт»: роботи й категорії ремонту."""

from PyQt5.QtWidgets import QButtonGroup, QHBoxLayout, QStackedWidget

from database.query import SortKey
from services import Topic
from services.export import ColumnKind
from ui.dialogs import CategoryForm, WorkTypeForm
from ui.filters import ChoiceFilter, FlagFilter, NumberRangeFilter
from ui.list_panel import ListPanel, make_button
from ui.messages import run_safely
from ui.pages.base import Page
from ui.table_model import ColumnSpec

WORK_COLUMNS = [
    ColumnSpec("name", "Робота", width=300, sort_field="name",
               stretch=True),
    ColumnSpec("category_name", "Категорія", width=170,
               sort_field="category_name"),
    ColumnSpec("price_kop", "Ціна, грн", ColumnKind.MONEY, 110,
               "price_kop"),
    ColumnSpec("norm_hours", "Нормо-години", ColumnKind.DECIMAL, 110,
               "norm_hours"),
    ColumnSpec("times_used", "Використано", ColumnKind.INTEGER, 110,
               "times_used"),
    ColumnSpec("is_active", "Активна", ColumnKind.BOOLEAN, 80, "is_active"),
]

CATEGORY_COLUMNS = [
    ColumnSpec("name", "Категорія", width=260, sort_field="name",
               stretch=True),
    ColumnSpec("work_types_count", "Робіт у прайсі", ColumnKind.INTEGER,
               140),
    ColumnSpec("parts_count", "Запчастин", ColumnKind.INTEGER, 120),
]


class CatalogPage(Page):
    TITLE = "Прайс робіт"
    SUBTITLE = "Роботи з цінами й нормо-годинами та категорії ремонту"
    TOPICS = frozenset({Topic.CATALOG, Topic.ORDERS, Topic.STOCK})

    def __init__(self, app, bridge, window):
        super().__init__(app, bridge, window)
        self.category_filter = ChoiceFilter("Категорія", "category_id",
                                            width=170)
        self.works = ListPanel(
            WORK_COLUMNS, "work_type_id", "Пошук: назва роботи, категорія",
            [self.category_filter,
             NumberRangeFilter("Ціна, грн", "price_kop", scale=100),
             FlagFilter("Лише активні", "is_active")],
            [("Назва", "name"), ("Категорія", "category_name"),
             ("Ціна", "price_kop"), ("Нормо-години", "norm_hours"),
             ("Використано", "times_used")],
            SortKey("category_name"),
            tone=lambda row: None if row["is_active"] else "inactive",
            empty_text="Прайс ще порожній")
        self.categories = ListPanel(
            CATEGORY_COLUMNS, "category_id", "Пошук категорії",
            empty_text="Категорій ще немає")
        self._build_switch()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.works)
        self.stack.addWidget(self.categories)
        self.body.addWidget(self.stack)
        self._build_actions()

    def _build_switch(self):
        switch = QHBoxLayout()
        switch.setSpacing(0)
        self.switch_group = QButtonGroup(self)
        for index, text in enumerate(("Роботи", "Категорії")):
            button = make_button(text)
            button.setCheckable(True)
            button.setProperty("segment", True)
            button.setProperty("first" if index == 0 else "last", True)
            self.switch_group.addButton(button, index)
            switch.addWidget(button)
        self.switch_group.button(0).setChecked(True)
        self.switch_group.idClicked.connect(self._switch)
        switch.addStretch()
        self.body.addLayout(switch)

    def _build_actions(self):
        self.add_button = make_button("Нова робота", "plus", "primary")
        self.add_button.clicked.connect(self._add)
        self.header_actions.addWidget(self.add_button)
        self.work_edit = make_button("Редагувати", "edit")
        self.work_delete = make_button("Видалити", "trash", "danger")
        export = make_button("Експорт", "export")
        for button in (self.work_edit, self.work_delete, export):
            self.works.add_action(button)
        self.work_edit.clicked.connect(self._edit_work)
        self.work_delete.clicked.connect(self._delete_work)
        export.clicked.connect(
            lambda: self.export(self.works, "work_types", "prais"))
        self.works.query_changed.connect(self.refresh)
        self.works.activated.connect(lambda _: self._edit_work())
        self.works.delete_requested.connect(self._delete_work)
        self.works.selection_changed.connect(
            lambda record_id: self._enable(record_id, self.work_edit,
                                           self.work_delete))

        self.category_edit = make_button("Редагувати", "edit")
        self.category_delete = make_button("Видалити", "trash", "danger")
        self.categories.add_action(self.category_edit)
        self.categories.add_action(self.category_delete)
        self.category_edit.clicked.connect(self._edit_category)
        self.category_delete.clicked.connect(self._delete_category)
        self.categories.query_changed.connect(self.refresh)
        self.categories.activated.connect(lambda _: self._edit_category())
        self.categories.delete_requested.connect(self._delete_category)
        self.categories.selection_changed.connect(
            lambda record_id: self._enable(record_id, self.category_edit,
                                           self.category_delete))

    @staticmethod
    def _enable(record_id, *buttons):
        for button in buttons:
            button.setEnabled(record_id is not None)

    def _switch(self, index: int):
        self.stack.setCurrentIndex(index)
        self.add_button.setText("Нова робота" if index == 0
                                else "Нова категорія")

    def refresh(self):
        self.category_filter.set_options(
            [(category.name, category.category_id)
             for category in self._app.catalog.categories()])
        self.load(self.works, self._app.catalog.find_work_types)
        self.load(self.categories, self._app.catalog.find_categories)

    # ---- дії ---------------------------------------------------------------

    def _add(self):
        form = WorkTypeForm(self._app, parent=self) \
            if self.stack.currentIndex() == 0 \
            else CategoryForm(self._app, parent=self)
        form.exec_()

    def _edit_work(self):
        work_id = self.works.selected_id()
        if work_id is None:
            return
        work = run_safely(self, lambda: self._app.catalog.get_work_type(
            work_id))
        if work:
            WorkTypeForm(self._app, work, self).exec_()

    def _delete_work(self):
        row = self.works.selected_row()
        if row:
            self.delete_record(
                "роботу", row["name"],
                lambda: self._app.catalog.delete_work_type(
                    row["work_type_id"]))

    def _edit_category(self):
        category_id = self.categories.selected_id()
        if category_id is None:
            return
        category = next((item for item in self._app.catalog.categories()
                         if item.category_id == category_id), None)
        if category:
            CategoryForm(self._app, category, self).exec_()

    def _delete_category(self):
        row = self.categories.selected_row()
        if row:
            self.delete_record(
                "категорію", row["name"],
                lambda: self._app.catalog.delete_category(
                    row["category_id"]))
