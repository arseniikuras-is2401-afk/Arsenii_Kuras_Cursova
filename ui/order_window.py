"""Вікно одного замовлення: шапка, роботи, запчастини, історія, статус."""

from datetime import date

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QTabWidget, QVBoxLayout, QWidget)

from models.errors import NotFoundError
from models.order import Order
from models.order_lines import LineKind
from models.order_state import OrderStatus
from services import AppContext, Topic
from services.export import ColumnKind
from ui import formatting
from ui.dialogs import (AddPartDialog, AddWorkDialog, CommentDialog,
                        OrderHeaderForm)
from ui.event_bridge import QtEventBridge
from ui.list_panel import DataTable, make_button, make_card
from ui.messages import confirm, run_safely
from ui.table_model import ColumnSpec, RecordTableModel
from ui.theme import STATUS_COLORS

_WORK_COLUMNS = [
    ColumnSpec("title", "Робота", width=330, stretch=True),
    ColumnSpec("quantity", "К-сть", ColumnKind.INTEGER, 70),
    ColumnSpec("price", "Ціна, грн", ColumnKind.MONEY, 110),
    ColumnSpec("total", "Сума, грн", ColumnKind.MONEY, 110),
    ColumnSpec("hours", "Н-год", ColumnKind.DECIMAL, 80),
]
_PART_COLUMNS = [
    ColumnSpec("title", "Запчастина", width=330, stretch=True),
    ColumnSpec("quantity", "К-сть", ColumnKind.INTEGER, 70),
    ColumnSpec("price", "Ціна, грн", ColumnKind.MONEY, 110),
    ColumnSpec("total", "Сума, грн", ColumnKind.MONEY, 110),
    ColumnSpec("stock", "Лишилось на складі", ColumnKind.INTEGER, 140),
]
_HISTORY_COLUMNS = [
    ColumnSpec("changed_at", "Коли", ColumnKind.DATETIME, 140),
    ColumnSpec("old_status", "Було", ColumnKind.STATUS, 170),
    ColumnSpec("new_status", "Стало", ColumnKind.STATUS, 170),
    ColumnSpec("comment", "Коментар", width=260, stretch=True),
]

# Підпис кнопки переходу; для «В роботі» залежить від поточного статусу.
_ACTIONS = {
    OrderStatus.IN_PROGRESS: "Почати роботу",
    OrderStatus.COMPLETED: "Завершити",
    OrderStatus.PAID: "Прийняти оплату",
    OrderStatus.CANCELLED: "Скасувати замовлення",
}


class StatusBadge(QLabel):
    """Мітка статусу у шапці вікна."""

    def show_status(self, code: str, overdue: bool):
        title = OrderStatus(code).title + (" · прострочено" if overdue
                                           else "")
        foreground, background = STATUS_COLORS["overdue" if overdue
                                                else code]
        self.setText(title)
        self.setStyleSheet(
            f"background:{background}; color:{foreground}; "
            f"border-radius:11px; padding:3px 12px; font-weight:600;")


class OrderWindow(QDialog):
    """Немодальне вікно замовлення; оновлюється само після змін даних."""

    closed = pyqtSignal(int)

    def __init__(self, app: AppContext, bridge: QtEventBridge, order_id: int,
                 parent=None):
        super().__init__(parent)
        self._app = app
        self._order_id = order_id
        self._order: Order | None = None
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(900, 720)
        self._build()
        bridge.changed.connect(self._on_data_changed)
        self.reload()

    # ---- побудова ---------------------------------------------------------

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        header = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("OrderTitle")
        self.badge = StatusBadge()
        header.addWidget(self.title)
        header.addSpacing(10)
        header.addWidget(self.badge)
        header.addStretch()
        self.edit_button = make_button("Змінити дані", "edit")
        self.edit_button.clicked.connect(self._edit_header)
        header.addWidget(self.edit_button)
        root.addLayout(header)
        root.addWidget(self._info_card())
        self.tabs = QTabWidget()
        self.works = self._lines_tab(_WORK_COLUMNS, "Додати роботу",
                                     self._add_work, LineKind.WORK)
        self.parts = self._lines_tab(_PART_COLUMNS, "Додати запчастину",
                                     self._add_part, LineKind.PART)
        self.history_model = RecordTableModel(_HISTORY_COLUMNS, "log_id")
        history = QWidget()
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(10, 10, 10, 10)
        history_layout.addWidget(DataTable(self.history_model))
        self.tabs.addTab(self.works["page"], "Роботи")
        self.tabs.addTab(self.parts["page"], "Запчастини")
        self.tabs.addTab(history, "Історія статусів")
        root.addWidget(self.tabs, 1)
        root.addWidget(self._totals_card())
        self.status_buttons = QHBoxLayout()
        self.status_buttons.setSpacing(8)
        bottom = QHBoxLayout()
        self.lock_hint = QLabel()
        self.lock_hint.setProperty("role", "hint")
        bottom.addWidget(self.lock_hint)
        bottom.addStretch()
        bottom.addLayout(self.status_buttons)
        close = make_button("Закрити")
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        root.addLayout(bottom)

    def _info_card(self) -> QFrame:
        card = make_card()
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        self.info: dict[str, QLabel] = {}
        fields = (("car", "Автомобіль"), ("client", "Клієнт"),
                  ("mechanic", "Механік"), ("accepted", "Прийнято"),
                  ("due", "Термін"), ("mileage", "Пробіг"),
                  ("complaint", "Скарга"))
        for index, (key, caption) in enumerate(fields):
            row, column = (index // 2, (index % 2) * 2) if key != "complaint" \
                else (3, 0)
            label = QLabel(caption)
            label.setProperty("role", "muted")
            value = QLabel()
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(label, row, column, Qt.AlignTop)
            span = 3 if key == "complaint" else 1
            grid.addWidget(value, row, column + 1, 1, span)
            self.info[key] = value
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        return card

    def _lines_tab(self, columns, add_text, add_handler,
                   kind: LineKind) -> dict:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        model = RecordTableModel(columns, "line_id")
        table = DataTable(model)
        layout.addWidget(table)
        buttons = QHBoxLayout()
        add = make_button(add_text, "plus", "primary")
        add.clicked.connect(add_handler)
        remove = make_button("Прибрати рядок", "trash", "danger")
        remove.clicked.connect(lambda: self._remove_line(kind, table, model))
        table.delete_pressed.connect(remove.click)
        table.selectionModel().selectionChanged.connect(
            lambda *_: self._update_buttons())
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        layout.addLayout(buttons)
        return {"page": page, "model": model, "table": table, "add": add,
                "remove": remove}

    def _totals_card(self) -> QFrame:
        card = make_card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)
        self.totals = QLabel()
        self.totals.setProperty("role", "muted")
        self.totals.setWordWrap(True)
        self.total_value = QLabel()
        self.total_value.setObjectName("TotalValue")
        caption = QLabel("Разом до сплати")
        caption.setProperty("role", "muted")
        layout.addWidget(self.totals, 1)
        layout.addWidget(caption)
        layout.addSpacing(8)
        layout.addWidget(self.total_value)
        return card

    # ---- дані --------------------------------------------------------------

    def reload(self):
        try:
            self._order = self._app.orders.get(self._order_id)
        except NotFoundError:
            self.close()
            return
        order = self._order
        self.setWindowTitle(f"Замовлення {order.number}")
        self.title.setText(f"Замовлення {order.number}")
        self.badge.show_status(order.status.value,
                               order.is_overdue(date.today()))
        car, client = order.car, order.car.owner
        self.info["car"].setText(car.display_name())
        self.info["client"].setText(
            f"{client.full_name()}, {formatting.phone(client.phone)}")
        self.info["mechanic"].setText(order.mechanic.full_name())
        self.info["accepted"].setText(
            formatting.datetime_text(order.accepted_at))
        self.info["due"].setText(formatting.date_text(order.due_date))
        self.info["mileage"].setText(
            f"{formatting.integer(order.intake_mileage_km)} км")
        self.info["complaint"].setText(order.complaint)
        self._fill_lines(order)
        self.history_model.set_rows(self._app.orders.history(self._order_id))
        self._fill_totals(order)
        self._build_status_buttons(order)
        self._update_buttons()

    def _fill_lines(self, order: Order):
        works = [{"line_id": line.line_id, "title": line.title(),
                  "quantity": line.quantity, "price": line.unit_price.kop,
                  "total": line.total().kop, "hours": line.labor_hours()}
                 for line in order.work_lines()]
        parts = [{"line_id": line.line_id, "title": line.title(),
                  "quantity": line.quantity, "price": line.unit_price.kop,
                  "total": line.total().kop,
                  "stock": line.part.stock_qty}
                 for line in order.part_lines()]
        self.works["model"].set_rows(works)
        self.parts["model"].set_rows(parts)
        self.tabs.setTabText(0, f"Роботи ({len(works)})")
        self.tabs.setTabText(1, f"Запчастини ({len(parts)})")

    def _fill_totals(self, order: Order):
        works = order.sum_of(LineKind.WORK)
        parts = order.sum_of(LineKind.PART)
        discount = order.discount_amount()
        text = (f"Роботи: {works}   ·   Запчастини: {parts}   ·   "
                f"Нормо-години: {formatting.number(order.labor_hours(), 2)}")
        if not discount.is_zero():
            text += (f"\nЗнижка −{discount} "
                     f"({order.discount_policy().describe()})")
        self.totals.setText(text)
        self.total_value.setText(str(order.total()))

    def _build_status_buttons(self, order: Order):
        while self.status_buttons.count():
            item = self.status_buttons.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        order_of = (OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED,
                    OrderStatus.PAID, OrderStatus.CANCELLED)
        allowed = order.state.allowed_next()
        for status in order_of:
            if status not in allowed:
                continue
            text = _ACTIONS[status]
            if status is OrderStatus.IN_PROGRESS \
                    and order.status is OrderStatus.COMPLETED:
                text = "Повернути на доопрацювання"
            variant = "danger" if status is OrderStatus.CANCELLED else (
                "primary" if status is not OrderStatus.IN_PROGRESS
                or order.status is OrderStatus.NEW else None)
            button = make_button(text, variant=variant)
            button.clicked.connect(
                lambda _, s=status: self._change_status(s))
            self.status_buttons.addWidget(button)

    def _update_buttons(self):
        if self._order is None:
            return
        state = self._order.state
        editable = state.lines_editable
        reason = "" if editable else state.locked_reason()
        self.lock_hint.setText(reason)
        self.edit_button.setEnabled(editable)
        self.edit_button.setToolTip(reason)
        for tab in (self.works, self.parts):
            tab["add"].setEnabled(editable)
            tab["add"].setToolTip(reason)
            has_selection = bool(
                tab["table"].selectionModel().selectedRows())
            tab["remove"].setEnabled(editable and has_selection)
            tab["remove"].setToolTip(reason if not editable else (
                "" if has_selection else "Виберіть рядок у таблиці"))

    def _on_data_changed(self, topics: frozenset):
        if topics & {Topic.ORDERS, Topic.STOCK, Topic.CATALOG, Topic.STAFF,
                     Topic.CARS, Topic.CLIENTS}:
            self.reload()

    # ---- дії ---------------------------------------------------------------

    def _edit_header(self):
        OrderHeaderForm(self._app, self._order, self).exec_()

    def _add_work(self):
        AddWorkDialog(self._app, self._order_id, self).exec_()

    def _add_part(self):
        AddPartDialog(self._app, self._order_id, self).exec_()

    def _remove_line(self, kind: LineKind, table: DataTable,
                     model: RecordTableModel):
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        row = model.row_data(rows[0].row())
        extra = ("\nЗапчастини буде повернуто на склад."
                 if kind is LineKind.PART else "")
        if confirm(self, "Прибрати рядок",
                   f"Прибрати «{row['title']}» із замовлення?{extra}",
                   "Прибрати", danger=True):
            run_safely(self, lambda: self._app.orders.remove_line(
                self._order_id, kind, row["line_id"]), "Рядок прибрано")

    def _change_status(self, status: OrderStatus):
        order = self._order
        comment = None
        if status is OrderStatus.CANCELLED:
            parts = sum(line.quantity for line in order.part_lines())
            note = (f" На склад повернеться запчастин: {parts} шт."
                    if parts else "")
            dialog = CommentDialog(
                "Скасування замовлення",
                f"Скасувати замовлення {order.number}?{note} Скасоване "
                f"замовлення не можна відновити.", "Скасувати замовлення",
                danger=True, parent=self)
            if not dialog.exec_():
                return
            comment = dialog.comment
        elif status is OrderStatus.IN_PROGRESS \
                and order.status is OrderStatus.COMPLETED:
            dialog = CommentDialog(
                "Повернення на доопрацювання",
                "Опишіть, що потрібно доробити.", "Повернути в роботу",
                required=True, parent=self)
            if not dialog.exec_():
                return
            comment = dialog.comment
        elif status is OrderStatus.PAID:
            if not confirm(self, "Оплата",
                           f"Прийняти оплату {order.total()} за замовлення "
                           f"{order.number}? Після цього замовлення не "
                           f"можна буде змінити.", "Прийняти оплату"):
                return
        run_safely(self, lambda: self._app.orders.change_status(
            self._order_id, status, comment),
            f"Статус: {status.title}")

    def closeEvent(self, event):
        self.closed.emit(self._order_id)
        super().closeEvent(event)
