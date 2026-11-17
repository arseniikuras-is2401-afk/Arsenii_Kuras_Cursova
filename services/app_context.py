"""Точка збирання: створює базу, події й усі сервіси застосунку."""

from pathlib import Path

from config import DATABASE_PATH
from database import Database
from database.setup import open_database
from services.base import Clock, system_clock
from services.catalog_service import CatalogService
from services.customer_service import CustomerService
from services.events import EventHub
from services.export import ExportService
from services.order_service import OrderService
from services.parts_import import PartsReceiptImporter
from services.report_service import ReportService
from services.staff_service import StaffService


class AppContext:
    """Містить усі сервіси й відповідає за закриття з'єднання з базою.

    Інтерфейс отримує сервіси лише звідси й не створює їх сам, тому всі
    сторінки працюють з тим самим набором сервісів і однією базою.
    """

    def __init__(self, database: Database, clock: Clock = system_clock):
        self.database = database
        self.events = EventHub()
        args = (database, self.events, clock)
        self.customers = CustomerService(*args)
        self.staff = StaffService(*args)
        self.catalog = CatalogService(*args)
        self.orders = OrderService(*args)
        self.reports = ReportService(*args)
        self.exports = ExportService(*args)
        self.parts_import = PartsReceiptImporter(*args)

    @classmethod
    def open(cls, path: Path | str = DATABASE_PATH) -> "AppContext":
        """Відкриває (за потреби створює й заповнює) файл бази."""
        return cls(open_database(path))

    def close(self):
        self.database.close()
