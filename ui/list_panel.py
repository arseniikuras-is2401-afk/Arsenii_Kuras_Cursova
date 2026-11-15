"""Панель списку: пошук, фільтри, сортування, таблиця й порожній стан."""

from collections.abc import Callable, Mapping, Sequence

from PyQt5.QtCore import QItemSelectionModel, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout,
                             QHeaderView, QLabel, QPushButton,
                             QStackedLayout, QTableView, QVBoxLayout,
                             QWidget)

from database.query import ListQuery, SortKey
from services.export import ColumnKind, ExportColumn
from ui import formatting
from ui.filters import FilterBar, FilterControl, SearchBox, SortBar
from ui.icons import icon
from ui.table_model import ColumnSpec, RecordTableModel, StatusDelegate

SEARCH_DELAY_MS = 300


def make_card(parent=None) -> QFrame:
    card = QFrame(parent)
    card.setProperty("card", True)
    return card


def make_button(text: str, icon_name: str | None = None,
                variant: str | None = None, tooltip: str = "") \
        -> QPushButton:
    """Кнопка в стилі застосунку; variant — primary, danger або ghost."""
    button = QPushButton(text)
    if icon_name:
        color = "#FFFFFF" if variant == "primary" else (
            "#C92A2A" if variant == "danger" else "#4A5466")
        button.setIcon(icon(icon_name, color, 16))
    if variant:
        button.setProperty("variant", variant)
    if tooltip:
        button.setToolTip(tooltip)
    button.setCursor(Qt.PointingHandCursor)
    return button


class DataTable(QTableView):
    """Таблиця тільки для перегляду з виділенням цілого рядка."""

    delete_pressed = pyqtSignal()
    enter_pressed = pyqtSignal()

    def __init__(self, model: RecordTableModel, parent=None):
        super().__init__(parent)
        self.setModel(model)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.setSortingEnabled(False)   # сортує SQL за двома ключами
        self.setFocusPolicy(Qt.StrongFocus)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(36)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Interactive)
        self._status_delegate = StatusDelegate(self)
        if any(column.stretch for column in model.columns):
            header.setStretchLastSection(False)
        for index, column in enumerate(model.columns):
            self.setColumnWidth(index, column.width)
            if column.stretch:
                header.setSectionResizeMode(index, QHeaderView.Stretch)
            if column.kind is ColumnKind.STATUS:
                self.setItemDelegateForColumn(index, self._status_delegate)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_pressed.emit()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.enter_pressed.emit()
            return
        super().keyPressEvent(event)


class ListPanel(QWidget):
    """Список записів однієї таблиці з керуванням вибіркою.

    Панель лише формує ListQuery й показує рядки; дані завантажує
    сторінка через сервіс, отримавши сигнал query_changed.
    """

    query_changed = pyqtSignal()
    selection_changed = pyqtSignal(object)   # id або None
    activated = pyqtSignal(int)
    delete_requested = pyqtSignal()

    def __init__(self, columns: Sequence[ColumnSpec], id_key: str,
                 search_placeholder: str | None = None,
                 filters: Sequence[FilterControl] = (),
                 sort_fields: Sequence[tuple[str, str]] = (),
                 default_sort: SortKey | None = None,
                 tone: Callable[[Mapping], str | None] | None = None,
                 empty_text: str = "Записів ще немає",
                 parent=None):
        super().__init__(parent)
        self.model = RecordTableModel(columns, id_key, tone, self)
        self.table = DataTable(self.model)
        self.search = SearchBox(search_placeholder) \
            if search_placeholder else None
        self.filter_bar = FilterBar(filters) if filters else None
        self.sort_bar = SortBar(sort_fields, default_sort) \
            if sort_fields and default_sort else None
        self._empty_text = empty_text
        self._search_timer = QTimer(self, singleShot=True,
                                    interval=SEARCH_DELAY_MS)
        self._build()
        self._connect()

    # ---- побудова ---------------------------------------------------------

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        if self.search or self.filter_bar or self.sort_bar:
            root.addWidget(self._controls_card())
        holder = QWidget()
        self._stack = QStackedLayout(holder)
        self._stack.addWidget(self.table)
        self._stack.addWidget(self._empty_widget())
        root.addWidget(holder, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        self.count_label = QLabel()
        self.count_label.setProperty("role", "hint")
        bottom = QHBoxLayout()
        bottom.addLayout(self.actions)
        bottom.addStretch()
        bottom.addWidget(self.count_label)
        root.addLayout(bottom)

    def _controls_card(self) -> QFrame:
        card = make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        top = QHBoxLayout()
        if self.search:
            top.addWidget(self.search, 1)
        if self.sort_bar:
            top.addSpacing(12)
            top.addWidget(self.sort_bar)
        if not self.search:
            top.addStretch()
        self.reset_button = make_button("Скинути", "reset", "ghost",
                                        "Очистити пошук, фільтри й "
                                        "сортування")
        top.addWidget(self.reset_button)
        layout.addLayout(top)
        if self.filter_bar:
            layout.addWidget(self.filter_bar)
        return card

    def _empty_widget(self) -> QWidget:
        widget = make_card()
        layout = QVBoxLayout(widget)
        layout.addStretch()
        self._empty_title = QLabel()
        self._empty_title.setProperty("role", "emptyTitle")
        self._empty_title.setAlignment(Qt.AlignCenter)
        self._empty_hint = QLabel()
        self._empty_hint.setProperty("role", "muted")
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_reset = make_button("Скинути пошук і фільтри", "reset")
        self._empty_reset.clicked.connect(self.reset)
        layout.addWidget(self._empty_title)
        layout.addWidget(self._empty_hint)
        layout.addSpacing(8)
        layout.addWidget(self._empty_reset, 0, Qt.AlignCenter)
        layout.addStretch()
        return widget

    def _connect(self):
        if self.search:
            self.search.textChanged.connect(self._search_timer.start)
            self.search.returnPressed.connect(self._emit_query_now)
            self._search_timer.timeout.connect(self.query_changed)
        if self.filter_bar:
            self.filter_bar.changed.connect(self.query_changed)
        if self.sort_bar:
            self.sort_bar.changed.connect(self.query_changed)
            self.table.horizontalHeader().sectionClicked.connect(
                self._on_header_clicked)
        if self.search or self.filter_bar or self.sort_bar:
            self.reset_button.clicked.connect(self.reset)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.selection_changed.emit(self.selected_id()))
        self.table.doubleClicked.connect(
            lambda index: self.activated.emit(self.model.id_at(index.row())))
        self.table.enter_pressed.connect(self._emit_activated)
        self.table.delete_pressed.connect(self.delete_requested)

    # ---- вибірка ------------------------------------------------------------

    def current_query(self) -> ListQuery:
        return ListQuery(
            search_text=self.search.text() if self.search else "",
            criteria=self.filter_bar.criteria() if self.filter_bar else [],
            sort_keys=self.sort_bar.sort_keys() if self.sort_bar else [])

    def has_conditions(self) -> bool:
        query = self.current_query()
        return bool(query.search_text.strip() or query.criteria)

    def reset(self):
        if self.search:
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        if self.filter_bar:
            self.filter_bar.reset()
        if self.sort_bar:
            self.sort_bar.reset()
        self.query_changed.emit()

    def _emit_query_now(self):
        self._search_timer.stop()
        self.query_changed.emit()

    def _on_header_clicked(self, section: int):
        field = self.model.columns[section].sort_field
        if field:
            self.sort_bar.set_primary(field)

    # ---- рядки -------------------------------------------------------------

    def set_rows(self, rows: Sequence[Mapping]):
        """Показує рядки й зберігає виділення, якщо запис лишився."""
        selected = self.selected_id()
        self.model.set_rows(rows)
        if rows:
            self._stack.setCurrentIndex(0)
            if selected is not None:
                self.select_id(selected)
        else:
            filtered = self.has_conditions()
            self._empty_title.setText("Нічого не знайдено" if filtered
                                      else self._empty_text)
            self._empty_hint.setText(
                "Змініть умови пошуку або скиньте фільтри" if filtered
                else "Додайте перший запис кнопкою внизу")
            self._empty_reset.setVisible(filtered)
            self._stack.setCurrentIndex(1)
        self.count_label.setText(formatting.plural(
            len(rows), "запис", "записи", "записів"))
        self.selection_changed.emit(self.selected_id())

    def selected_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        return self.model.id_at(rows[0].row()) if rows else None

    def selected_row(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        return self.model.row_data(rows[0].row()) if rows else None

    def select_id(self, record_id: int):
        row = self.model.row_of(record_id)
        if row is None:
            return
        index = self.model.index(row, 0)
        self.table.selectionModel().select(
            index, QItemSelectionModel.ClearAndSelect
            | QItemSelectionModel.Rows)
        self.table.scrollTo(index)

    def export_columns(self) -> list[ExportColumn]:
        return [column.export_column() for column in self.model.columns]

    def add_action(self, button: QPushButton):
        self.actions.addWidget(button)

    def _emit_activated(self):
        record_id = self.selected_id()
        if record_id is not None:
            self.activated.emit(record_id)
