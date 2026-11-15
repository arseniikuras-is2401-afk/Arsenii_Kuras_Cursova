"""Модель таблиці для QTableView і мітки статусів."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate

from services.export import ColumnKind, ExportColumn
from ui import formatting
from ui.theme import PALETTE, STATUS_COLORS

ID_ROLE = Qt.UserRole + 1      # id запису в базі
RAW_ROLE = Qt.UserRole + 2     # значення без форматування
TONE_ROLE = Qt.UserRole + 3    # «тон» рядка: overdue, low, inactive

_RIGHT = (ColumnKind.MONEY, ColumnKind.INTEGER, ColumnKind.DECIMAL)


@dataclass(frozen=True)
class ColumnSpec:
    """Стовпець таблиці: ключ рядка, заголовок, вид значення, ширина.

    Той самий опис використовується для експорту, тож файл містить ті
    самі стовпці, що бачить користувач.
    """

    key: str
    title: str
    kind: ColumnKind = ColumnKind.TEXT
    width: int = 120
    sort_field: str | None = None   # поле ListQuery; None — не сортується
    stretch: bool = False           # забирає вільну ширину таблиці

    def display(self, row: Mapping) -> str:
        value = row[self.key]
        if value is None:
            return ""
        match self.kind:
            case ColumnKind.MONEY:
                return formatting.money(value)
            case ColumnKind.INTEGER:
                return formatting.integer(value)
            case ColumnKind.DECIMAL:
                return formatting.number(value, 2)
            case ColumnKind.BOOLEAN:
                return "✓" if value else ""
            case ColumnKind.STATUS:
                return formatting.status_title(value)
            case ColumnKind.PHONE:
                return formatting.phone(value)
            case ColumnKind.DATE:
                return formatting.date_text(value)
            case ColumnKind.DATETIME:
                return formatting.datetime_text(value)
        return str(value)

    def export_column(self) -> ExportColumn:
        return ExportColumn(self.key, self.title, self.kind)


def tone_is(tone: Callable | None, row: Mapping, expected: str) -> bool:
    return tone is not None and tone(row) == expected


class RecordTableModel(QAbstractTableModel):
    """Рядки з бази у вигляді таблиці. Кожен рядок знає свій id, тож
    сортування й фільтри не плутають записи."""

    def __init__(self, columns: Sequence[ColumnSpec], id_key: str,
                 tone: Callable[[Mapping], str | None] | None = None,
                 parent=None):
        super().__init__(parent)
        self._columns = list(columns)
        self._id_key = id_key
        self._tone = tone
        self._rows: list[dict] = []

    @property
    def columns(self) -> list[ColumnSpec]:
        return self._columns

    def set_rows(self, rows: Sequence[Mapping]):
        self.beginResetModel()
        self._rows = [dict(row) for row in rows]
        self.endResetModel()

    def rows(self) -> list[dict]:
        return self._rows

    def row_data(self, row: int) -> dict:
        return self._rows[row]

    def id_at(self, row: int) -> int:
        return self._rows[row][self._id_key]

    def row_of(self, record_id: int) -> int | None:
        for index, row in enumerate(self._rows):
            if row[self._id_key] == record_id:
                return index
        return None

    # ---- QAbstractTableModel ------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = self._columns[index.column()]
        if role == Qt.DisplayRole:
            return column.display(row)
        if role == Qt.ToolTipRole:
            text = column.display(row)
            return text if len(text) > 24 else None
        if role == Qt.TextAlignmentRole:
            horizontal = Qt.AlignRight if column.kind in _RIGHT else (
                Qt.AlignHCenter if column.kind is ColumnKind.BOOLEAN
                else Qt.AlignLeft)
            return int(horizontal | Qt.AlignVCenter)
        if role == ID_ROLE:
            return row[self._id_key]
        if role == RAW_ROLE:
            return row[column.key]
        if role == TONE_ROLE:
            return self._tone(row) if self._tone else None
        if role == Qt.ForegroundRole:
            tone = self._tone(row) if self._tone else None
            if tone == "inactive":
                return QColor(PALETTE["faint"])
            if tone == "low" and column.key == "stock_qty":
                return QColor(PALETTE["danger"])
        if role == Qt.FontRole and tone_is(self._tone, row, "low") \
                and column.key == "stock_qty":
            font = QFont()
            font.setWeight(QFont.DemiBold)
            return font
        return None

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._columns[section].title
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole:
            kind = self._columns[section].kind
            horizontal = Qt.AlignRight if kind in _RIGHT else Qt.AlignLeft
            return int(horizontal | Qt.AlignVCenter)
        return None


class StatusDelegate(QStyledItemDelegate):
    """Малює статус замовлення кольоровою міткою з заокругленими кутами.

    Прострочене відкрите замовлення отримує червону мітку.
    """

    def paint(self, painter: QPainter, option, index: QModelIndex):
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        option.text = ""
        if style:
            style.drawControl(QStyle.CE_ItemViewItem, option, painter,
                              option.widget)
        code = index.data(RAW_ROLE)
        if not code:
            return
        overdue = index.data(TONE_ROLE) == "overdue"
        # У вузькому стовпці прострочене відкрите замовлення позначається
        # одним словом; повний статус видно у вікні замовлення.
        text = "Прострочено" if overdue else formatting.status_title(code)
        foreground, background = STATUS_COLORS["overdue" if overdue
                                                else code]
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont(option.font)
        font.setPointSizeF(option.font.pointSizeF() - 0.5)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 18
        height = metrics.height() + 6
        rect = QRectF(option.rect.left() + 8,
                      option.rect.center().y() - height / 2 + 1,
                      min(width, option.rect.width() - 12), height)
        path = QPainterPath()
        path.addRoundedRect(rect, height / 2, height / 2)
        painter.fillPath(path, QColor(background))
        painter.setPen(QColor(foreground))
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()
