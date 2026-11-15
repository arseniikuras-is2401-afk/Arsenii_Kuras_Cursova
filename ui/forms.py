"""Декларативні форми: поле описується об'єктом FieldSpec, а FormDialog
будує з таких описів діалог, читає значення й показує помилки."""

from collections.abc import Callable, Sequence
from datetime import date

from PyQt5.QtCore import QDate, QLocale, Qt
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDateEdit,
                             QDialog, QDoubleSpinBox, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                             QSpinBox, QVBoxLayout, QWidget)

from models.errors import AutoServiceError, ValidationError
from models.money import Money
from models.validators import format_phone
from ui.filters import set_invalid
from ui.list_panel import make_button
from ui.messages import show_error as show_unexpected_error

UKRAINIAN = QLocale(QLocale.Ukrainian, QLocale.Ukraine)

# ---- описи полів ------------------------------------------------------------


class FieldSpec:
    """Поле форми: як створити віджет, прочитати й записати значення.

    Нащадки перевизначають create_widget(), read() і write(). Форма
    працює з усіма полями однаково (поліморфізм), тому новий вид поля
    не вимагає змін у FormDialog.
    """

    def __init__(self, name: str, label: str, required: bool = False,
                 hint: str = ""):
        self.name = name
        self.label = label
        self.required = required
        self.hint = hint

    def create_widget(self) -> QWidget:
        raise NotImplementedError

    def read(self, widget: QWidget):
        raise NotImplementedError

    def write(self, widget: QWidget, value):
        raise NotImplementedError

    def is_filled(self, widget: QWidget) -> bool:
        """Чи заповнено поле (для активності кнопки «Зберегти»)."""
        return True

    def change_signal(self, widget: QWidget):
        """Сигнал зміни значення: форма оновлює стан кнопки й прибирає
        позначку помилки, щойно користувач виправляє поле."""
        return None


class TextField(FieldSpec):
    def __init__(self, name: str, label: str, required: bool = False,
                 hint: str = "", placeholder: str = "",
                 max_length: int = 120):
        super().__init__(name, label, required, hint)
        self.placeholder = placeholder
        self.max_length = max_length

    def create_widget(self) -> QWidget:
        edit = QLineEdit()
        edit.setPlaceholderText(self.placeholder)
        edit.setMaxLength(self.max_length)
        return edit

    def read(self, widget: QLineEdit):
        return widget.text().strip()

    def write(self, widget: QLineEdit, value):
        widget.setText("" if value is None else str(value))

    def is_filled(self, widget: QLineEdit) -> bool:
        return bool(widget.text().strip())

    def change_signal(self, widget: QLineEdit):
        return widget.textChanged


class PhoneField(TextField):
    """Телефон: приймає будь-який запис, модель нормалізує до 0XXXXXXXXX."""

    def __init__(self, name: str = "phone", label: str = "Телефон",
                 required: bool = True):
        super().__init__(name, label, required,
                         hint="Можна з пробілами або +38",
                         placeholder="067 123 45 67", max_length=20)

    def write(self, widget: QLineEdit, value):
        widget.setText(format_phone(value) if value else "")


class MultilineField(FieldSpec):
    def __init__(self, name: str, label: str, required: bool = False,
                 hint: str = "", placeholder: str = "", max_length: int = 500):
        super().__init__(name, label, required, hint)
        self.placeholder = placeholder
        self.max_length = max_length

    def create_widget(self) -> QWidget:
        edit = QPlainTextEdit()
        edit.setPlaceholderText(self.placeholder)
        edit.setFixedHeight(76)
        edit.setTabChangesFocus(True)
        return edit

    def read(self, widget: QPlainTextEdit):
        return widget.toPlainText().strip()[:self.max_length]

    def write(self, widget: QPlainTextEdit, value):
        widget.setPlainText(value or "")

    def is_filled(self, widget: QPlainTextEdit) -> bool:
        return bool(widget.toPlainText().strip())

    def change_signal(self, widget: QPlainTextEdit):
        return widget.textChanged


class IntField(FieldSpec):
    def __init__(self, name: str, label: str, minimum: int = 0,
                 maximum: int = 10**6, suffix: str = "", hint: str = "",
                 step: int = 1):
        super().__init__(name, label, False, hint)
        self.minimum, self.maximum = minimum, maximum
        self.suffix, self.step = suffix, step

    def create_widget(self) -> QWidget:
        spin = QSpinBox()
        spin.setRange(self.minimum, self.maximum)
        spin.setSingleStep(self.step)
        spin.setGroupSeparatorShown(True)
        spin.setLocale(UKRAINIAN)
        if self.suffix:
            spin.setSuffix(f" {self.suffix}")
        spin.setMinimumWidth(130)
        return spin

    def read(self, widget: QSpinBox):
        return widget.value()

    def write(self, widget: QSpinBox, value):
        widget.setValue(int(value or 0))

    def change_signal(self, widget: QSpinBox):
        return widget.valueChanged


class DecimalField(FieldSpec):
    def __init__(self, name: str, label: str, minimum: float,
                 maximum: float, decimals: int = 2, step: float = 0.1,
                 suffix: str = "", hint: str = ""):
        super().__init__(name, label, False, hint)
        self.minimum, self.maximum = minimum, maximum
        self.decimals, self.step, self.suffix = decimals, step, suffix

    def create_widget(self) -> QWidget:
        spin = QDoubleSpinBox()
        spin.setLocale(UKRAINIAN)
        spin.setDecimals(self.decimals)
        spin.setRange(self.minimum, self.maximum)
        spin.setSingleStep(self.step)
        if self.suffix:
            spin.setSuffix(f" {self.suffix}")
        spin.setMinimumWidth(130)
        return spin

    def read(self, widget: QDoubleSpinBox):
        return round(widget.value(), self.decimals)

    def write(self, widget: QDoubleSpinBox, value):
        widget.setValue(float(value or 0))

    def change_signal(self, widget: QDoubleSpinBox):
        return widget.valueChanged


class MoneyField(TextField):
    """Сума в гривнях; читається як Money, некоректний текст — помилка
    саме цього поля."""

    def __init__(self, name: str = "price", label: str = "Ціна, грн",
                 required: bool = True):
        super().__init__(name, label, required, placeholder="0,00",
                         max_length=16)

    def create_widget(self) -> QWidget:
        edit = super().create_widget()
        edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        edit.setMaximumWidth(160)
        return edit

    def read(self, widget: QLineEdit):
        return Money.from_text(widget.text(), field=self.name)

    def write(self, widget: QLineEdit, value):
        widget.setText(value.to_text(with_currency=False)
                       .replace(" ", " ") if value else "")


class DateField(FieldSpec):
    def __init__(self, name: str, label: str, hint: str = "",
                 minimum: date | None = None):
        super().__init__(name, label, False, hint)
        self.minimum = minimum

    def create_widget(self) -> QWidget:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd.MM.yyyy")
        edit.setLocale(UKRAINIAN)
        edit.setDate(QDate.currentDate())
        if self.minimum:
            edit.setMinimumDate(QDate(self.minimum))
        edit.setMinimumWidth(130)
        return edit

    def read(self, widget: QDateEdit) -> date:
        return widget.date().toPyDate()

    def write(self, widget: QDateEdit, value):
        if value:
            widget.setDate(QDate(value))

    def change_signal(self, widget: QDateEdit):
        return widget.dateChanged


class ChoiceField(FieldSpec):
    """Вибір пов'язаного об'єкта за зрозумілою назвою, з пошуком."""

    def __init__(self, name: str, label: str,
                 options: Callable[[], Sequence[tuple[str, object]]],
                 required: bool = True, hint: str = "",
                 empty_text: str | None = None):
        super().__init__(name, label, required, hint)
        self.options = options
        self.empty_text = empty_text

    def create_widget(self) -> QWidget:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        combo.completer().setFilterMode(Qt.MatchContains)
        combo.completer().setCaseSensitivity(Qt.CaseInsensitive)
        combo.setMinimumWidth(320)
        self.fill(combo, self.options())
        return combo

    def fill(self, combo: QComboBox, options: Sequence[tuple[str, object]]):
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        if self.empty_text is not None:
            combo.addItem(self.empty_text, None)
        for text, value in options:
            combo.addItem(text, value)
        index = combo.findData(current) if current is not None else -1
        combo.setCurrentIndex(index if index >= 0 else
                              (0 if combo.count() else -1))
        combo.blockSignals(False)
        combo.currentIndexChanged.emit(combo.currentIndex())

    def read(self, widget: QComboBox):
        # Текст, введений вручну без вибору зі списку, не рахується.
        index = widget.findText(widget.currentText(), Qt.MatchExactly)
        return widget.itemData(index) if index >= 0 else None

    def write(self, widget: QComboBox, value):
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)

    def is_filled(self, widget: QComboBox) -> bool:
        return self.read(widget) is not None

    def change_signal(self, widget: QComboBox):
        return widget.currentIndexChanged


class CheckField(FieldSpec):
    def __init__(self, name: str, text: str, hint: str = ""):
        super().__init__(name, "", False, hint)
        self.text = text

    def create_widget(self) -> QWidget:
        return QCheckBox(self.text)

    def read(self, widget: QCheckBox) -> bool:
        return widget.isChecked()

    def write(self, widget: QCheckBox, value):
        widget.setChecked(bool(value))

    def change_signal(self, widget: QCheckBox):
        return widget.toggled


# ---- діалог форми -----------------------------------------------------------


class FormDialog(QDialog):
    """Діалог, побудований зі списку полів.

    Нащадки перевизначають fields() і submit(values). Якщо submit кидає
    ValidationError з назвою поля, помилка показується під цим полем;
    інші помилки — у червоній смужці вгорі. Вікно не закривається, а
    введені значення лишаються для виправлення.
    """

    SUBMIT_TEXT = "Зберегти"
    SUBMIT_VARIANT = "primary"

    def __init__(self, title: str, parent=None, intro: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)
        self._specs: list[FieldSpec] = self.fields()
        self._widgets: dict[str, QWidget] = {}
        self._errors: dict[str, QLabel] = {}
        self._build(title, intro)
        self._update_submit()

    # ---- для нащадків -------------------------------------------------------

    def fields(self) -> list[FieldSpec]:
        raise NotImplementedError

    def submit(self, values: dict):
        """Зберігає дані; виняток означає, що зберегти не вдалося."""
        raise NotImplementedError

    # ---- побудова ---------------------------------------------------------

    def _build(self, title: str, intro: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        heading = QLabel(title)
        heading.setProperty("role", "sectionTitle")
        root.addWidget(heading)
        if intro:
            intro_label = QLabel(intro)
            intro_label.setProperty("role", "muted")
            intro_label.setWordWrap(True)
            root.addWidget(intro_label)
        self.banner = QLabel()
        self.banner.setProperty("role", "banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        root.addWidget(self.banner)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(6)
        for spec in self._specs:
            widget = spec.create_widget()
            self._widgets[spec.name] = widget
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(widget)
            error = QLabel()
            error.setProperty("role", "fieldError")
            error.setWordWrap(True)
            error.hide()
            self._errors[spec.name] = error
            box.addWidget(error)
            if spec.hint:
                hint = QLabel(spec.hint)
                hint.setProperty("role", "hint")
                hint.setWordWrap(True)
                box.addWidget(hint)
            label = f"{spec.label} *" if spec.required else spec.label
            form.addRow(label, box)
            signal = spec.change_signal(widget)
            if signal is not None:
                signal.connect(lambda *_, n=spec.name: self._on_changed(n))
        root.addLayout(form)
        self.extra = QVBoxLayout()
        root.addLayout(self.extra)
        root.addStretch()
        buttons = QHBoxLayout()
        note = QLabel("* — обов'язкові поля")
        note.setProperty("role", "hint")
        note.setVisible(any(spec.required for spec in self._specs))
        buttons.addWidget(note)
        buttons.addStretch()
        cancel = make_button("Скасувати")
        cancel.clicked.connect(self.reject)
        self.submit_button = make_button(self.SUBMIT_TEXT,
                                         variant=self.SUBMIT_VARIANT)
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.submit_button)
        root.addLayout(buttons)

    # ---- значення й помилки -------------------------------------------------

    def widget(self, name: str) -> QWidget:
        return self._widgets[name]

    def spec(self, name: str) -> FieldSpec:
        return next(spec for spec in self._specs if spec.name == name)

    def set_values(self, values: dict):
        for spec in self._specs:
            if spec.name in values:
                spec.write(self._widgets[spec.name], values[spec.name])
        self._update_submit()

    def values(self) -> dict:
        """Читає всі поля; некоректне значення — ValidationError поля."""
        return {spec.name: spec.read(self._widgets[spec.name])
                for spec in self._specs}

    def show_error(self, error: Exception):
        field = getattr(error, "field", None)
        message = getattr(error, "message", str(error))
        if field in self._errors:
            self._errors[field].setText(message)
            self._errors[field].show()
            set_invalid(self._widgets[field], True)
            self._widgets[field].setFocus()
        else:
            self.banner.setText(message)
            self.banner.show()

    def _clear_errors(self):
        self.banner.hide()
        for name, label in self._errors.items():
            label.hide()
            set_invalid(self._widgets[name], False)

    def _on_changed(self, name: str):
        if self._errors[name].isVisible():
            self._errors[name].hide()
            set_invalid(self._widgets[name], False)
        self._update_submit()

    def _update_submit(self):
        filled = all(spec.is_filled(self._widgets[spec.name])
                     for spec in self._specs if spec.required)
        self.submit_button.setEnabled(filled)
        self.submit_button.setToolTip(
            "" if filled else "Заповніть обов'язкові поля, позначені *")

    def accept(self):
        self._clear_errors()
        try:
            self.submit(self.values())
        except (ValidationError, AutoServiceError) as error:
            self.show_error(error)
            return
        except Exception as error:   # база або файл: показуємо й лишаємось
            show_unexpected_error(self, error)
            return
        super().accept()
