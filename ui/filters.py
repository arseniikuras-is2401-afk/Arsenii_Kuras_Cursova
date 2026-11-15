"""Елементи пошуку, фільтрації та сортування над таблицями.

Кожен фільтр — окремий віджет зі спільним інтерфейсом criterion() і
reset(), тож панель фільтрів опитує їх однаково, не знаючи їхнього типу.
"""

from collections.abc import Callable, Sequence
from datetime import date, timedelta

from PyQt5.QtCore import QDate, QLocale, Qt, pyqtSignal
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QSizePolicy,
                             QWidget)

from database.query import Between, Criterion, Equals, IsTrue, SortKey
from ui.icons import icon


def _label(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "muted")
    return label


def set_invalid(widget: QWidget, invalid: bool, tooltip: str = ""):
    """Червона рамка поля (властивість invalid у style.qss)."""
    widget.setProperty("invalid", invalid)
    widget.setToolTip(tooltip if invalid else "")
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class FilterControl(QWidget):
    """Базовий фільтр. Нащадки повертають умову або None, якщо фільтр не
    задано. (Не ABC: метаклас ABC несумісний з метакласом Qt.)"""

    changed = pyqtSignal()

    def __init__(self, field: str, parent=None):
        super().__init__(parent)
        self.field = field
        # Фільтр займає рівно стільки місця, скільки потрібно його полям.
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

    def criterion(self) -> Criterion | None:
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError

    def is_active(self) -> bool:
        return self.criterion() is not None


class ChoiceFilter(FilterControl):
    """Вибір одного значення зі списку; перший пункт — «Усі»."""

    def __init__(self, label: str, field: str,
                 options: Sequence[tuple[str, object]] = (),
                 all_text: str = "Усі", width: int = 150):
        super().__init__(field)
        self._all_text = all_text
        self.combo = QComboBox()
        self.combo.setMinimumWidth(width)
        self._layout.addWidget(_label(label))
        self._layout.addWidget(self.combo)
        self.set_options(options)
        self.combo.currentIndexChanged.connect(self.changed)

    def set_options(self, options: Sequence[tuple[str, object]]):
        """Оновлює варіанти, зберігаючи вибране значення, якщо воно є."""
        current = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(self._all_text, None)
        for text, value in options:
            self.combo.addItem(text, value)
        index = self.combo.findData(current) if current is not None else 0
        self.combo.setCurrentIndex(max(index, 0))
        self.combo.blockSignals(False)

    def criterion(self) -> Criterion | None:
        value = self.combo.currentData()
        return None if value is None else Equals(self.field, value)

    def reset(self):
        self.combo.setCurrentIndex(0)


class PeriodFilter(FilterControl):
    """Період з готовими варіантами («7 днів», «Цей місяць») або свій."""

    PRESETS = ("Весь час", "Сьогодні", "Останні 7 днів", "Останні 30 днів",
               "Цей місяць", "Минулий місяць", "Свій період…")
    CUSTOM = len(PRESETS) - 1

    def __init__(self, label: str, field: str,
                 today: Callable[[], date] = date.today):
        super().__init__(field)
        self._today = today
        self.combo = QComboBox()
        self.combo.addItems(self.PRESETS)
        self.start = self._date_edit()
        self.end = self._date_edit()
        self._dash = QLabel("–")
        self._layout.addWidget(_label(label))
        self._layout.addWidget(self.combo)
        self._layout.addWidget(self.start)
        self._layout.addWidget(self._dash)
        self._layout.addWidget(self.end)
        self.combo.currentIndexChanged.connect(self._on_preset)
        self.start.dateChanged.connect(self._on_dates)
        self.end.dateChanged.connect(self._on_dates)
        self._show_custom(False)

    def _date_edit(self) -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd.MM.yyyy")
        edit.setLocale(QLocale(QLocale.Ukrainian, QLocale.Ukraine))
        edit.setDate(QDate.currentDate())
        return edit

    def _show_custom(self, visible: bool):
        for widget in (self.start, self._dash, self.end):
            widget.setVisible(visible)

    def _on_preset(self, index: int):
        self._show_custom(index == self.CUSTOM)
        self.changed.emit()

    def _on_dates(self):
        self._validate()
        if self.combo.currentIndex() == self.CUSTOM:
            self.changed.emit()

    def _validate(self) -> bool:
        valid = self.start.date() <= self.end.date()
        set_invalid(self.end, not valid,
                    "Кінець періоду раніше за початок")
        return valid

    def period(self) -> tuple[date, date] | None:
        today = self._today()
        index = self.combo.currentIndex()
        if index == 1:
            return today, today
        if index == 2:
            return today - timedelta(days=6), today
        if index == 3:
            return today - timedelta(days=29), today
        if index == 4:
            return today.replace(day=1), today
        if index == 5:
            last = today.replace(day=1) - timedelta(days=1)
            return last.replace(day=1), last
        if index == self.CUSTOM and self._validate():
            return (self.start.date().toPyDate(), self.end.date().toPyDate())
        return None

    def criterion(self) -> Criterion | None:
        period = self.period()
        if period is None:
            return None
        return Between(self.field, period[0].isoformat(),
                       period[1].isoformat())

    def reset(self):
        self.combo.setCurrentIndex(0)


class NumberRangeFilter(FilterControl):
    """Числовий діапазон «від – до»; будь-яку межу можна лишити порожньою.

    `scale` переводить введене значення в одиниці бази (гривні → копійки).
    """

    def __init__(self, label: str, field: str, scale: int = 1,
                 decimals: int = 2):
        super().__init__(field)
        self._scale = scale
        self.low = self._edit("від", decimals)
        self.high = self._edit("до", decimals)
        self._layout.addWidget(_label(label))
        self._layout.addWidget(self.low)
        self._layout.addWidget(QLabel("–"))
        self._layout.addWidget(self.high)

    def _edit(self, placeholder: str, decimals: int) -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setFixedWidth(78)
        validator = QDoubleValidator(0, 10**9, decimals, edit)
        validator.setNotation(QDoubleValidator.StandardNotation)
        validator.setLocale(QLocale(QLocale.Ukrainian, QLocale.Ukraine))
        edit.setValidator(validator)
        edit.textChanged.connect(self._on_change)
        return edit

    def _value(self, edit: QLineEdit) -> float | None:
        text = edit.text().replace(" ", "").replace(",", ".")
        try:
            return float(text) if text else None
        except ValueError:
            return None

    def _on_change(self):
        self._bounds()
        self.changed.emit()

    def _bounds(self) -> tuple[float | None, float | None] | None:
        low, high = self._value(self.low), self._value(self.high)
        valid = low is None or high is None or low <= high
        set_invalid(self.high, not valid, "Верхня межа менша за нижню")
        return (low, high) if valid else None

    def criterion(self) -> Criterion | None:
        bounds = self._bounds()
        if bounds is None or bounds == (None, None):
            return None
        low, high = (None if value is None else round(value * self._scale)
                     for value in bounds)
        return Between(self.field, low, high)

    def reset(self):
        self.low.clear()
        self.high.clear()


class FlagFilter(FilterControl):
    """Позначка «лише …»."""

    def __init__(self, text: str, field: str):
        super().__init__(field)
        self.check = QCheckBox(text)
        self._layout.addWidget(self.check)
        self.check.toggled.connect(self.changed)

    def criterion(self) -> Criterion | None:
        return IsTrue(self.field) if self.check.isChecked() else None

    def set_checked(self, checked: bool):
        self.check.setChecked(checked)

    def reset(self):
        self.check.setChecked(False)


class FilterBar(QWidget):
    """Рядок фільтрів; разом вони дають умови для WHERE через AND."""

    changed = pyqtSignal()

    def __init__(self, controls: Sequence[FilterControl], parent=None):
        super().__init__(parent)
        self.controls = list(controls)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        for control in self.controls:
            layout.addWidget(control)
            control.changed.connect(self.changed)
        layout.addStretch()

    def criteria(self) -> list[Criterion]:
        found = (control.criterion() for control in self.controls)
        return [criterion for criterion in found if criterion is not None]

    def reset(self):
        for control in self.controls:
            control.blockSignals(True)
            control.reset()
            control.blockSignals(False)


class SortBar(QWidget):
    """Сортування за двома полями з пріоритетом і напрямком."""

    changed = pyqtSignal()

    def __init__(self, fields: Sequence[tuple[str, str]],
                 default: SortKey, parent=None):
        super().__init__(parent)
        self._fields = list(fields)
        self._default = default
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.primary = QComboBox()
        self.secondary = QComboBox()
        self.primary.setMinimumWidth(150)
        self.secondary.setMinimumWidth(150)
        self.secondary.addItem("—", None)
        for title, field in self._fields:
            self.primary.addItem(title, field)
            self.secondary.addItem(title, field)
        self.primary_direction = self._direction_button()
        self.secondary_direction = self._direction_button()
        layout.addWidget(_label("Сортування"))
        layout.addWidget(self.primary)
        layout.addWidget(self.primary_direction)
        layout.addSpacing(8)
        layout.addWidget(_label("потім"))
        layout.addWidget(self.secondary)
        layout.addWidget(self.secondary_direction)
        self.primary.currentIndexChanged.connect(self.changed)
        self.secondary.currentIndexChanged.connect(self._on_secondary)
        self.reset()
        self._on_secondary()

    def _direction_button(self) -> QPushButton:
        button = QPushButton()
        button.setObjectName("SortDirection")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.toggled.connect(lambda checked, b=button: self._show(b))
        button.toggled.connect(self.changed)
        self._show(button)
        return button

    @staticmethod
    def _show(button: QPushButton):
        descending = button.isChecked()
        button.setText("↓" if descending else "↑")
        button.setToolTip("За спаданням (Я→А, 9→1)" if descending
                          else "За зростанням (А→Я, 1→9)")

    def _on_secondary(self):
        self.secondary_direction.setEnabled(
            self.secondary.currentData() is not None)
        self.changed.emit()

    def sort_keys(self) -> list[SortKey]:
        keys = [SortKey(self.primary.currentData(),
                        self.primary_direction.isChecked())]
        second = self.secondary.currentData()
        if second is not None and second != keys[0].field:
            keys.append(SortKey(second,
                                self.secondary_direction.isChecked()))
        return keys

    def set_primary(self, field: str):
        """Клік по заголовку: поле стає першим; повторний клік — напрямок."""
        index = self.primary.findData(field)
        if index < 0:
            return
        if self.primary.currentIndex() == index:
            self.primary_direction.toggle()
        else:
            self.blockSignals(True)
            self.primary.setCurrentIndex(index)
            self.primary_direction.setChecked(False)
            self.blockSignals(False)
            self.changed.emit()

    def reset(self):
        self.blockSignals(True)
        self.primary.setCurrentIndex(
            max(self.primary.findData(self._default.field), 0))
        self.primary_direction.setChecked(self._default.descending)
        self.secondary.setCurrentIndex(0)
        self.secondary_direction.setChecked(False)
        self.blockSignals(False)


class SearchBox(QLineEdit):
    """Поле пошуку з піктограмою й кнопкою очищення."""

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(icon("search", "#98A2B3"), QLineEdit.LeadingPosition)
        self.setMinimumWidth(260)
