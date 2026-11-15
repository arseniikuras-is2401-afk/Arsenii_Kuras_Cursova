"""Сторінка «Склад»: запчастини, прихід, імпорт накладної."""

from pathlib import Path

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from database.query import SortKey
from services import Topic
from services.export import ColumnKind
from ui.dialogs import PartForm, ReceivePartsDialog
from ui.filters import ChoiceFilter, FlagFilter, NumberRangeFilter
from ui.list_panel import ListPanel, make_button
from ui.messages import run_safely
from ui.pages.base import Page
from ui.table_model import ColumnSpec

COLUMNS = [
    ColumnSpec("article", "Артикул", width=130, sort_field="article"),
    ColumnSpec("name", "Назва", width=280, sort_field="name",
               stretch=True),
    ColumnSpec("category_name", "Категорія", width=170,
               sort_field="category_name"),
    ColumnSpec("price_kop", "Ціна, грн", ColumnKind.MONEY, 110,
               "price_kop"),
    ColumnSpec("stock_qty", "Залишок, шт.", ColumnKind.INTEGER, 110,
               "stock_qty"),
    ColumnSpec("min_qty", "Мінімум, шт.", ColumnKind.INTEGER, 110,
               "min_qty"),
]


class StockPage(Page):
    TITLE = "Склад"
    SUBTITLE = "Запчастини, залишки й прихід від постачальників"
    TOPICS = frozenset({Topic.STOCK, Topic.CATALOG})

    def __init__(self, app, bridge, window):
        super().__init__(app, bridge, window)
        self.category_filter = ChoiceFilter("Категорія", "category_id",
                                            width=170)
        self.low_filter = FlagFilter("Лише нижче мінімуму", "is_low")
        self.panel = ListPanel(
            COLUMNS, "part_id", "Пошук: артикул або назва",
            [self.category_filter,
             NumberRangeFilter("Ціна, грн", "price_kop", scale=100),
             self.low_filter],
            [("Назва", "name"), ("Артикул", "article"),
             ("Залишок", "stock_qty"), ("Ціна", "price_kop"),
             ("Категорія", "category_name")],
            SortKey("name"),
            tone=lambda row: "low" if row["is_low"] else None,
            empty_text="Склад порожній")
        add = make_button("Нова запчастина", "plus", "primary")
        add.clicked.connect(lambda: PartForm(self._app, parent=self).exec_())
        import_button = make_button("Імпорт накладної", "import",
                                    tooltip="Прихід запчастин із CSV")
        import_button.clicked.connect(self._import)
        self.header_actions.addWidget(import_button)
        self.header_actions.addWidget(add)
        self.receive_button = make_button("Прихід", "receive")
        self.edit_button = make_button("Редагувати", "edit")
        self.delete_button = make_button("Видалити", "trash", "danger")
        export = make_button("Експорт", "export")
        for button in (self.receive_button, self.edit_button,
                       self.delete_button, export):
            self.panel.add_action(button)
        self.receive_button.clicked.connect(self._receive)
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)
        export.clicked.connect(
            lambda: self.export(self.panel, "parts", "sklad"))
        self.panel.query_changed.connect(self.refresh)
        self.panel.activated.connect(lambda _: self._edit())
        self.panel.delete_requested.connect(self._delete)
        self.panel.selection_changed.connect(self._update_buttons)
        self.body.addWidget(self.panel)

    def refresh(self):
        self.category_filter.set_options(
            [(category.name, category.category_id)
             for category in self._app.catalog.categories()])
        self.load(self.panel, self._app.catalog.find_parts)

    def show_low_stock(self):
        """Перехід із головної сторінки: лише запчастини нижче мінімуму."""
        self.panel.filter_bar.reset()
        self.low_filter.set_checked(True)

    def _update_buttons(self, part_id):
        for button in (self.receive_button, self.edit_button,
                       self.delete_button):
            button.setEnabled(part_id is not None)

    def _part(self):
        part_id = self.panel.selected_id()
        if part_id is None:
            return None
        return run_safely(self, lambda: self._app.catalog.get_part(part_id))

    def _receive(self):
        part = self._part()
        if part:
            ReceivePartsDialog(self._app, part, self).exec_()

    def _edit(self):
        part = self._part()
        if part:
            PartForm(self._app, part, self).exec_()

    def _delete(self):
        row = self.panel.selected_row()
        if row:
            self.delete_record(
                "запчастину", row["name"],
                lambda: self._app.catalog.delete_part(row["part_id"]))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Накладна постачальника", str(Path.home()),
            "CSV (*.csv);;Усі файли (*)")
        if not path:
            return
        report = run_safely(self, lambda: self._app.parts_import.import_file(
            path))
        if not report or report is True:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Результат імпорту")
        box.setIcon(QMessageBox.Information if not report.errors
                    else QMessageBox.Warning)
        box.setText(report.summary())
        details = report.errors + report.warnings
        if details:
            box.setInformativeText("Рядки з помилками не імпортовано, "
                                   "решту збережено. Перелік рядків — у "
                                   "подробицях.")
            box.setDetailedText("\n".join(details))
        box.exec_()
