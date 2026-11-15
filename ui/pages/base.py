"""Базовий клас сторінки головного вікна."""

from datetime import date
from pathlib import Path

from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QVBoxLayout,
                             QWidget)

from services import AppContext, Topic
from ui.event_bridge import QtEventBridge
from ui.list_panel import ListPanel
from ui.messages import confirm, notify, run_safely, show_error


class Page(QWidget):
    """Сторінка з заголовком, яка сама оновлюється після змін даних.

    TOPICS — теми подій, від яких залежить сторінка. Видима сторінка
    оновлюється одразу, прихована лише позначається застарілою й
    оновиться, коли її відкриють: зайвих запитів до бази немає.
    """

    TITLE = ""
    SUBTITLE = ""
    TOPICS: frozenset[Topic] = frozenset()

    def __init__(self, app: AppContext, bridge: QtEventBridge, window):
        super().__init__()
        self.setObjectName("PageRoot")
        self._app = app
        self._window = window
        self._stale = True
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(16)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel(self.TITLE)
        title.setProperty("role", "pageTitle")
        titles.addWidget(title)
        if self.SUBTITLE:
            self.subtitle = QLabel(self.SUBTITLE)
            self.subtitle.setProperty("role", "muted")
            titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(8)
        header.addLayout(self.header_actions)
        root.addLayout(header)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        root.addLayout(self.body, 1)
        bridge.changed.connect(self.on_topics_changed)

    # ---- оновлення ---------------------------------------------------------

    def refresh(self):
        """Перечитує дані сторінки з бази."""
        raise NotImplementedError

    def safe_refresh(self):
        try:
            self.refresh()
            self._stale = False
        except Exception as error:   # сторінка лишається працездатною
            show_error(self, error)

    def on_topics_changed(self, topics: frozenset):
        if not topics & self.TOPICS:
            return
        if self.isVisible():
            self.safe_refresh()
        else:
            self._stale = True

    def showEvent(self, event):
        super().showEvent(event)
        if self._stale:
            self.safe_refresh()

    # ---- спільні дії --------------------------------------------------------

    def load(self, panel: ListPanel, finder):
        """Завантажує рядки панелі за її поточною вибіркою."""
        try:
            panel.set_rows(finder(panel.current_query()))
        except ValueError as error:
            show_error(self, error)

    def export(self, panel: ListPanel, source: str, file_stem: str):
        """Зберігає поточну вибірку таблиці в CSV або JSON."""
        suggested = Path.home() / f"{file_stem}_{date.today():%Y-%m-%d}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Експорт таблиці", str(suggested),
            "CSV для Excel (*.csv);;JSON (*.json)")
        if not path:
            return
        count = run_safely(self, lambda: self._app.exports.export(
            source, panel.current_query(), panel.export_columns(), path))
        if count is not None:
            notify(self, f"Експортовано {count} рядків у {Path(path).name}")

    def delete_record(self, what: str, name: str, action,
                      consequences: str = "") -> bool:
        """Запитує підтвердження (за замовчуванням «Скасувати») і видаляє."""
        text = f"Видалити {what} «{name}»?"
        if consequences:
            text += f"\n\n{consequences}"
        text += "\n\nЦю дію не можна скасувати."
        if not confirm(self, "Підтвердження видалення", text, "Видалити",
                       danger=True):
            return False
        return run_safely(self, action, "Запис видалено") is not None
