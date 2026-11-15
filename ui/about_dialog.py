"""Вікно «Про програму» з даними про автора курсового проєкту."""

import sqlite3
import sys

from PyQt5.QtCore import PYQT_VERSION_STR, Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from config import (APP_TITLE, APP_VERSION, AUTHOR_FULL, COLLEGE,
                    DISCIPLINE, PROJECT_TOPIC, PROJECT_YEAR)
from ui.icons import icon
from ui.list_panel import make_button
from ui.theme import PALETTE


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Про програму")
        self.setFixedWidth(520)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(10)
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon("wrench_logo", PALETTE["accent"], 40, 2)
                       .pixmap(40, 40))
        titles = QVBoxLayout()
        name = QLabel(APP_TITLE)
        name.setProperty("role", "pageTitle")
        version = QLabel(f"Версія {APP_VERSION}")
        version.setProperty("role", "muted")
        titles.addWidget(name)
        titles.addWidget(version)
        header.addWidget(logo)
        header.addSpacing(10)
        header.addLayout(titles)
        header.addStretch()
        root.addLayout(header)
        root.addSpacing(6)
        for caption, value in (
                ("Курсовий проєкт з дисципліни", f"«{DISCIPLINE}»"),
                ("Тема", PROJECT_TOPIC),
                ("Виконав", AUTHOR_FULL),
                ("Навчальний заклад", f"{COLLEGE}, {PROJECT_YEAR}")):
            label = QLabel(caption)
            label.setProperty("role", "hint")
            text = QLabel(value)
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if caption == "Виконав":
                text.setStyleSheet("font-weight:600; font-size:11pt;")
            root.addWidget(label)
            root.addWidget(text)
        tech = QLabel(
            f"Python {sys.version.split()[0]} · PyQt {PYQT_VERSION_STR} · "
            f"SQLite {sqlite3.sqlite_version} · Matplotlib")
        tech.setProperty("role", "hint")
        root.addSpacing(6)
        root.addWidget(tech)
        close = make_button("Закрити", variant="primary")
        close.clicked.connect(self.accept)
        root.addWidget(close, 0, Qt.AlignRight)
