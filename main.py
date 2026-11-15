"""Точка входу застосунку «Автосервіс» (курсовий проєкт, Курас Арсеній)."""

import logging
import sys

from PyQt5.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PyQt5.QtWidgets import QApplication, QMessageBox

from config import APP_TITLE, DATABASE_PATH
from services import AppContext
from ui.main_window import MainWindow
from ui.theme import apply_theme


def _install_translations(app: QApplication) -> QTranslator:
    """Українські підписи стандартних кнопок і діалогів Qt."""
    QLocale.setDefault(QLocale(QLocale.Ukrainian, QLocale.Ukraine))
    translator = QTranslator(app)
    if translator.load("qtbase_uk",
                       QLibraryInfo.location(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
    return translator


def main() -> int:
    """Відкриває базу (за потреби створює демо-дані) і головне вікно."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    _install_translations(app)
    apply_theme(app)
    try:
        context = AppContext.open(DATABASE_PATH)
    except Exception as error:   # без бази працювати неможливо
        logging.exception("Не вдалося відкрити базу")
        QMessageBox.critical(
            None, APP_TITLE,
            f"Не вдалося відкрити базу даних {DATABASE_PATH}.\n\n{error}")
        return 1
    window = MainWindow(context)
    window.show()
    try:
        return app.exec_()
    finally:
        context.close()


if __name__ == "__main__":
    sys.exit(main())
