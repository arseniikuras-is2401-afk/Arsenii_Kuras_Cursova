"""Головне вікно: бічна навігація, сторінки, вікна замовлень, сповіщення."""

from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                             QMainWindow, QPushButton, QShortcut,
                             QStackedWidget, QVBoxLayout, QWidget)

from config import APP_TITLE, AUTHOR_SHORT, PROJECT_YEAR
from services import AppContext
from ui.about_dialog import AboutDialog
from ui.dialogs import NewOrderForm
from ui.event_bridge import QtEventBridge
from ui.icons import icon
from ui.order_window import OrderWindow
from ui.pages.base import Page
from ui.pages.cars import CarsPage
from ui.pages.catalog import CatalogPage
from ui.pages.clients import ClientsPage
from ui.pages.dashboard import DashboardPage
from ui.pages.orders import OrdersPage
from ui.pages.staff import StaffPage
from ui.pages.statistics import StatisticsPage
from ui.pages.stock import StockPage
from ui.theme import PALETTE

# (ключ, підпис, піктограма, клас сторінки)
PAGES = (
    ("dashboard", "Головна", "home", DashboardPage),
    ("orders", "Замовлення", "orders", OrdersPage),
    ("clients", "Клієнти", "clients", ClientsPage),
    ("cars", "Автомобілі", "car", CarsPage),
    ("staff", "Механіки", "staff", StaffPage),
    ("catalog", "Прайс робіт", "price", CatalogPage),
    ("stock", "Склад", "stock", StockPage),
    ("statistics", "Статистика", "chart", StatisticsPage),
)


class NavigationBar(QFrame):
    """Темна бічна панель: назва, розділи, автор проєкту."""

    def __init__(self, on_select, on_about):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 18, 0, 16)
        layout.setSpacing(2)
        brand = QHBoxLayout()
        brand.setContentsMargins(18, 0, 18, 0)
        logo = QLabel()
        logo.setPixmap(icon("wrench_logo", PALETTE["accent_bright"], 26, 2)
                       .pixmap(26, 26))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("Автосервіс")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("облік замовлень і складу")
        subtitle.setObjectName("BrandSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        brand.addWidget(logo)
        brand.addSpacing(6)
        brand.addLayout(titles)
        layout.addLayout(brand)
        layout.addSpacing(22)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for number, (key, text, icon_name, _) in enumerate(PAGES, start=1):
            button = QPushButton(f"  {text}")
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setIcon(icon(icon_name, PALETTE["sidebar_text"], 18))
            button.setToolTip(f"Ctrl+{number}")
            button.clicked.connect(lambda _, k=key: on_select(k))
            self.group.addButton(button)
            self.buttons[key] = button
            layout.addWidget(button)
        layout.addStretch()
        footer = QVBoxLayout()
        footer.setContentsMargins(18, 0, 18, 0)
        footer.setSpacing(2)
        caption = QLabel(f"Курсовий проєкт · {PROJECT_YEAR}")
        caption.setObjectName("SidebarFooter")
        author = QLabel(AUTHOR_SHORT)
        author.setObjectName("SidebarAuthor")
        about = QPushButton("Про програму")
        about.setObjectName("AboutButton")
        about.setCursor(Qt.PointingHandCursor)
        about.clicked.connect(on_about)
        footer.addWidget(caption)
        footer.addWidget(author)
        footer.addSpacing(8)
        footer.addWidget(about, 0, Qt.AlignLeft)
        layout.addLayout(footer)

    def select(self, key: str):
        self.buttons[key].setChecked(True)


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext):
        super().__init__()
        self._app = context
        self._bridge = QtEventBridge(context.events, self)
        self._order_windows: dict[int, OrderWindow] = {}
        self.setWindowTitle(f"{APP_TITLE} — {AUTHOR_SHORT}")
        self.resize(1360, 820)
        self.setMinimumSize(1100, 660)
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.navigation = NavigationBar(self.show_page, self._about)
        self.stack = QStackedWidget()
        self.stack.setObjectName("Pages")
        self.pages: dict[str, Page] = {}
        for key, _, _, page_class in PAGES:
            page = page_class(context, self._bridge, self)
            self.pages[key] = page
            self.stack.addWidget(page)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._toast = QLabel(self)
        self._toast.setObjectName("Toast")
        self._toast.hide()
        self._toast_timer = QTimer(self, singleShot=True, interval=3500)
        self._toast_timer.timeout.connect(self._toast.hide)
        self._shortcuts()
        self.show_page("dashboard")

    def _shortcuts(self):
        for number, (key, *_rest) in enumerate(PAGES, start=1):
            QShortcut(QKeySequence(f"Ctrl+{number}"), self,
                      lambda k=key: self.show_page(k))
        QShortcut(QKeySequence("Ctrl+N"), self, lambda: self.new_order())

    # ---- навігація ----------------------------------------------------------

    def show_page(self, key: str):
        self.navigation.select(key)
        self.stack.setCurrentWidget(self.pages[key])

    def show_overdue_orders(self):
        self.pages["orders"].show_overdue()
        self.show_page("orders")

    def show_low_stock(self):
        self.pages["stock"].show_low_stock()
        self.show_page("stock")

    # ---- замовлення ---------------------------------------------------------

    def new_order(self, car_id: int | None = None):
        form = NewOrderForm(self._app, car_id, self)
        if form.exec_() and form.order_id:
            self.show_toast("Замовлення оформлено")
            self.open_order(form.order_id)

    def open_order(self, order_id: int):
        """Відкриває вікно замовлення або піднімає вже відкрите."""
        window = self._order_windows.get(order_id)
        if window is None:
            window = OrderWindow(self._app, self._bridge, order_id, self)
            window.closed.connect(
                lambda closed_id: self._order_windows.pop(closed_id, None))
            self._order_windows[order_id] = window
        window.show()
        window.raise_()
        window.activateWindow()

    # ---- службове -----------------------------------------------------------

    def show_toast(self, text: str):
        self._toast.setText(text)
        self._toast.adjustSize()
        margin = 24
        self._toast.move(QPoint(self.width() - self._toast.width() - margin,
                                self.height() - self._toast.height()
                                - margin))
        self._toast.show()
        self._toast.raise_()
        self._toast_timer.start()

    def _about(self):
        AboutDialog(self).exec_()

    def closeEvent(self, event):
        for window in list(self._order_windows.values()):
            window.close()
        self._bridge.detach()
        super().closeEvent(event)
