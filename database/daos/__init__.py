"""Класи доступу до окремих таблиць."""

from database.daos.catalog import (CategoryDao, EmployeeDao, PartDao,
                                   WorkTypeDao)
from database.daos.clients import CarDao, ClientDao
from database.daos.orders import OrderDao
from database.daos.reports import ReportDao

__all__ = ["CarDao", "CategoryDao", "ClientDao", "EmployeeDao", "OrderDao",
           "PartDao", "ReportDao", "WorkTypeDao"]
