"""Повідомлення користувачу: підтвердження, помилки, сповіщення."""

import logging
import sqlite3
from collections.abc import Callable

from PyQt5.QtWidgets import QMessageBox, QWidget

from models.errors import AutoServiceError

log = logging.getLogger(__name__)


def confirm(parent: QWidget, title: str, text: str,
            yes_text: str = "Так", danger: bool = False) -> bool:
    """Питання з кнопкою «Ні» за замовчуванням, щоб випадковий Enter
    нічого не видалив."""
    box = QMessageBox(QMessageBox.Warning if danger else QMessageBox.Question,
                      title, text, parent=parent)
    yes = box.addButton(yes_text, QMessageBox.YesRole)
    no = box.addButton("Скасувати", QMessageBox.NoRole)
    yes.setProperty("variant", "danger" if danger else "primary")
    yes.style().unpolish(yes)
    yes.style().polish(yes)
    box.setDefaultButton(no)
    box.exec_()
    return box.clickedButton() is yes


def show_error(parent: QWidget, error: Exception):
    """Пояснює помилку. Очікувані помилки — попередження, решта — критичні,
    але програма продовжує роботу."""
    if isinstance(error, AutoServiceError):
        QMessageBox.warning(parent, "Дію не виконано", error.message)
        return
    if isinstance(error, sqlite3.Error):
        log.exception("Помилка бази даних")
        QMessageBox.critical(
            parent, "Помилка бази даних",
            "Не вдалося виконати запит до бази даних. Зміни не збережено.\n\n"
            f"Подробиці: {error}")
        return
    if isinstance(error, OSError):
        QMessageBox.critical(parent, "Помилка файлу",
                             f"Не вдалося працювати з файлом: {error}")
        return
    log.exception("Неочікувана помилка")
    QMessageBox.critical(
        parent, "Неочікувана помилка",
        "Під час виконання дії сталася помилка. Зміни не збережено.\n\n"
        f"{type(error).__name__}: {error}")


def run_safely(parent: QWidget, action: Callable, success: str | None = None):
    """Виконує дію; помилку показує, успіх — коротким сповіщенням.

    Повертає результат дії або None, якщо дія не вдалася.
    """
    try:
        result = action()
    except Exception as error:   # показуємо будь-яку помилку, не падаємо
        show_error(parent, error)
        return None
    if success:
        notify(parent, success)
    return result if result is not None else True


def notify(widget: QWidget, text: str):
    """Коротке сповіщення внизу головного вікна (якщо воно є)."""
    window = widget.window()
    owner = window.parentWidget().window() if window.parentWidget() \
        else window
    for candidate in (window, owner):
        if hasattr(candidate, "show_toast"):
            candidate.show_toast(text)
            return
