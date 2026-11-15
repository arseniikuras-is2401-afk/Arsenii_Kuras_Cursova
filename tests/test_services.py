"""Тести сервісів: бізнес-правила, транзакції, події, імпорт і експорт."""

import csv
import json
from datetime import date, timedelta

import pytest

from database import Equals, ListQuery
from database.daos.orders import OrderDao
from models import (BusinessRuleError, Car, Client, Employee,
                    InsufficientStockError, InvalidTransitionError, LineKind,
                    Money, OrderStatus, RecordInUseError, ValidationError)
from services import EventHub, Topic
from services.export import ColumnKind, ExportColumn, exporter_for

TODAY = date(2026, 11, 14)
DUE = TODAY + timedelta(days=2)


def _record_events(app) -> list[frozenset]:
    received = []
    app.events.subscribe(list(Topic), received.append)
    return received


def _open_order(app, shop, **extra) -> int:
    return app.orders.create(shop.car.car_id, shop.mechanic.employee_id,
                             "Скрип гальм", DUE, 151_000, **extra)


def _stock(app, shop) -> int:
    return app.catalog.get_part(shop.part.part_id).stock_qty


# ---- події ------------------------------------------------------------------

def test_hub_delivers_only_subscribed_topics_once():
    hub = EventHub()
    stock_events, all_events = [], []
    hub.subscribe([Topic.STOCK], stock_events.append)
    hub.subscribe([Topic.ORDERS, Topic.STOCK], all_events.append)
    hub.publish(Topic.ORDERS, Topic.STOCK)
    hub.publish(Topic.CLIENTS)
    assert len(stock_events) == 1
    assert len(all_events) == 1
    hub.unsubscribe(all_events.append)


def test_failed_operation_publishes_nothing(app, shop):
    events = _record_events(app)
    with pytest.raises(ValidationError):
        app.customers.save_client(Client("Мельник", "Оксана", "0671234567"))
    assert events == []


# ---- клієнти й авто ---------------------------------------------------------

def test_duplicate_phone_names_the_field_and_keeps_new_id_empty(app, shop):
    client = Client("Мельник", "Оксана", "067 123 45 67")
    with pytest.raises(ValidationError) as error:
        app.customers.save_client(client)
    assert error.value.field == "phone"
    assert client.client_id is None


def test_client_with_car_cannot_be_deleted(app, shop):
    with pytest.raises(RecordInUseError, match="автомобілів: 1"):
        app.customers.delete_client(shop.client.client_id)


def test_new_client_without_cars_can_be_deleted(app, shop):
    client = Client("Мельник", "Оксана", "0661112233")
    client_id = app.customers.save_client(client)
    events = _record_events(app)
    app.customers.delete_client(client_id)
    assert Topic.CLIENTS in events[0]
    assert len(app.customers.find_clients()) == 1


def test_mileage_cannot_be_reduced_by_editing(app, shop):
    car = app.customers.get_car(shop.car.car_id)
    edited = Car(car.owner, car.make, car.model, car.production_year,
                 car.plate_number, mileage_km=100_000, car_id=car.car_id)
    with pytest.raises(ValidationError) as error:
        app.customers.save_car(edited)
    assert error.value.field == "mileage_km"


def test_duplicate_plate_is_rejected(app, shop):
    car = Car(shop.client, "Kia", "Rio", 2020, "ат1234вс")
    with pytest.raises(ValidationError, match="держномером"):
        app.customers.save_car(car)


# ---- оформлення замовлення --------------------------------------------------

def test_second_open_order_for_car_is_rejected(app, shop):
    _open_order(app, shop)
    with pytest.raises(BusinessRuleError, match="АС-000001"):
        _open_order(app, shop)


def test_busy_mechanic_cannot_take_fifth_order(app, shop):
    for number in range(4):
        car = Car(shop.client, "Kia", "Rio", 2020, f"AT000{number}AA")
        app.customers.save_car(car)
        app.orders.create(car.car_id, shop.mechanic.employee_id,
                          "Планове ТО", DUE, 0)
    with pytest.raises(BusinessRuleError, match="максимум 4"):
        _open_order(app, shop)
    free = [employee for employee, _ in app.staff.available_mechanics()]
    assert free == []


def test_inactive_mechanic_cannot_take_order(app, shop):
    app.staff.set_active(shop.mechanic.employee_id, False)
    with pytest.raises(BusinessRuleError, match="неактивний"):
        _open_order(app, shop)


def test_mechanic_with_open_orders_cannot_be_deactivated(app, shop):
    _open_order(app, shop)
    with pytest.raises(BusinessRuleError, match="Передайте"):
        app.staff.set_active(shop.mechanic.employee_id, False)


def test_mechanic_in_history_cannot_be_deleted(app, shop):
    _open_order(app, shop)
    with pytest.raises(RecordInUseError, match="Деактивуйте"):
        app.staff.delete(shop.mechanic.employee_id)


def test_new_order_is_logged_and_numbered(app, shop):
    order_id = _open_order(app, shop)
    order = app.orders.get(order_id)
    assert order.number == "АС-000001"
    assert order.accepted_at.date() == TODAY
    history = app.orders.history(order_id)
    assert [row["new_status"] for row in history] == ["new"]


def test_loyal_client_gets_discount_on_works(app, shop):
    for _ in range(5):
        order_id = _open_order(app, shop)
        app.orders.add_work(order_id, shop.work.work_type_id, 1)
        for status in (OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED,
                       OrderStatus.PAID):
            app.orders.change_status(order_id, status)
    assert app.orders.loyalty_percent(shop.client.client_id) == 5
    order = app.orders.get(_open_order(app, shop))
    assert order.loyalty_discount_pct == 5


# ---- рядки замовлення -------------------------------------------------------

def test_adding_part_updates_stock_and_notifies(app, shop):
    order_id = _open_order(app, shop)
    events = _record_events(app)
    app.orders.add_part(order_id, shop.part.part_id, 2)
    app.orders.add_part(order_id, shop.part.part_id, 1)
    assert _stock(app, shop) == 2
    order = app.orders.get(order_id)
    assert [line.quantity for line in order.part_lines()] == [3]
    assert all(Topic.STOCK in topics for topics in events)


def test_too_many_parts_change_nothing(app, shop):
    order_id = _open_order(app, shop)
    with pytest.raises(InsufficientStockError, match="лише 5"):
        app.orders.add_part(order_id, shop.part.part_id, 6)
    assert _stock(app, shop) == 5
    assert app.orders.get(order_id).lines() == ()


def test_removing_part_line_returns_stock(app, shop):
    order_id = _open_order(app, shop)
    line = app.orders.add_part(order_id, shop.part.part_id, 2)
    app.orders.remove_line(order_id, LineKind.PART, line.line_id)
    assert _stock(app, shop) == 5


def test_header_discount_above_limit_is_rejected(app, shop):
    order_id = _open_order(app, shop)
    with pytest.raises(ValidationError) as error:
        app.orders.update_header(order_id, shop.mechanic.employee_id, DUE,
                                 "Скрип гальм", 31)
    assert error.value.field == "manual_discount_pct"


# ---- статуси ----------------------------------------------------------------

def test_full_path_updates_car_and_history(app, shop):
    order_id = _open_order(app, shop)
    app.orders.add_work(order_id, shop.work.work_type_id, 1)
    for status in (OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED,
                   OrderStatus.PAID):
        app.orders.change_status(order_id, status)
    assert app.customers.get_car(shop.car.car_id).mileage_km == 151_000
    assert len(app.orders.history(order_id)) == 4
    with pytest.raises(BusinessRuleError, match="Оплачене"):
        app.orders.add_work(order_id, shop.work.work_type_id, 1)


def test_wrong_transition_is_rejected(app, shop):
    order_id = _open_order(app, shop)
    with pytest.raises(InvalidTransitionError):
        app.orders.change_status(order_id, OrderStatus.PAID)


def test_cancel_returns_parts_to_stock(app, shop):
    order_id = _open_order(app, shop)
    app.orders.add_part(order_id, shop.part.part_id, 4)
    app.orders.change_status(order_id, OrderStatus.CANCELLED, "Відмова")
    assert _stock(app, shop) == 5
    assert app.orders.history(order_id)[-1]["comment"] == "Відмова"


def test_failure_inside_cancel_leaves_everything_as_was(app, shop,
                                                        monkeypatch):
    order_id = _open_order(app, shop)
    app.orders.add_part(order_id, shop.part.part_id, 4)

    def broken_log(*args, **kwargs):
        raise RuntimeError("збій запису історії")

    monkeypatch.setattr(OrderDao, "log_status", broken_log)
    with pytest.raises(RuntimeError):
        app.orders.change_status(order_id, OrderStatus.CANCELLED)
    monkeypatch.undo()
    assert app.orders.get(order_id).status is OrderStatus.NEW
    assert _stock(app, shop) == 1


def test_only_new_or_cancelled_order_can_be_deleted(app, shop):
    order_id = _open_order(app, shop)
    app.orders.add_work(order_id, shop.work.work_type_id, 1)
    app.orders.add_part(order_id, shop.part.part_id, 2)
    app.orders.change_status(order_id, OrderStatus.IN_PROGRESS)
    with pytest.raises(BusinessRuleError, match="спершу скасуйте"):
        app.orders.delete(order_id)


def test_deleting_new_order_returns_parts(app, shop):
    order_id = _open_order(app, shop)
    app.orders.add_part(order_id, shop.part.part_id, 2)
    app.orders.delete(order_id)
    assert _stock(app, shop) == 5
    assert app.orders.find() == []


def test_deleting_cancelled_order_does_not_return_parts_twice(app, shop):
    order_id = _open_order(app, shop)
    app.orders.add_part(order_id, shop.part.part_id, 2)
    app.orders.change_status(order_id, OrderStatus.CANCELLED)
    app.orders.delete(order_id)
    assert _stock(app, shop) == 5


# ---- склад і довідники ------------------------------------------------------

def test_receiving_parts(app, shop):
    app.catalog.receive_parts(shop.part.part_id, 10)
    assert _stock(app, shop) == 15


def test_editing_part_card_keeps_stock(app, shop):
    part = app.catalog.get_part(shop.part.part_id)
    part.price = Money.from_uah("1300")
    app.catalog.save_part(part)
    app.orders.add_part(_open_order(app, shop), part.part_id, 1)
    stale = app.catalog.get_part(part.part_id)
    assert stale.stock_qty == 4
    assert stale.price == Money.from_uah("1300")


def test_used_work_type_cannot_be_deleted(app, shop):
    app.orders.add_work(_open_order(app, shop), shop.work.work_type_id, 1)
    with pytest.raises(RecordInUseError, match="Активна"):
        app.catalog.delete_work_type(shop.work.work_type_id)


def test_category_in_use_cannot_be_deleted(app, shop):
    with pytest.raises(RecordInUseError, match="запчастин: 1"):
        app.catalog.delete_category(shop.category.category_id)


# ---- звіти ------------------------------------------------------------------

def test_revenue_by_month_fills_empty_months(app, shop):
    order_id = _open_order(app, shop)
    app.orders.add_work(order_id, shop.work.work_type_id, 2)
    for status in (OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED,
                   OrderStatus.PAID):
        app.orders.change_status(order_id, status)
    points = app.reports.revenue_by_month(date(2026, 9, 1), TODAY)
    assert [point.label for point in points] == ["вер 2026", "жов 2026",
                                                 "лис 2026"]
    assert [point.value for point in points] == [0, 0, 900.0]
    summary = app.reports.dashboard()
    assert summary.revenue_month == Money.from_uah("900")
    assert summary.average_check == Money.from_uah("900")


def test_reversed_period_is_rejected(app):
    with pytest.raises(ValidationError):
        app.reports.mechanic_load(TODAY, TODAY - timedelta(days=1))


# ---- експорт ----------------------------------------------------------------

EXPORT_COLUMNS = [
    ExportColumn("order_number", "Номер"),
    ExportColumn("status", "Статус", ColumnKind.STATUS),
    ExportColumn("total_kop", "Сума, грн", ColumnKind.MONEY),
    ExportColumn("is_overdue", "Прострочено", ColumnKind.BOOLEAN),
]


def test_csv_export_is_readable_by_excel(app, shop, tmp_path):
    order_id = _open_order(app, shop)
    app.orders.add_part(order_id, shop.part.part_id, 1)
    path = tmp_path / "orders.csv"
    count = app.exports.export("orders", ListQuery(), EXPORT_COLUMNS, path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")       # BOM для Excel
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines(),
                           delimiter=";"))
    assert count == 1
    assert rows[0] == ["Номер", "Статус", "Сума, грн", "Прострочено"]
    assert rows[1] == ["АС-000001", "Нове", "1250,00", "ні"]


def test_json_export_keeps_types_and_filter(app, shop, tmp_path):
    first = _open_order(app, shop)
    app.orders.change_status(first, OrderStatus.CANCELLED)
    _open_order(app, shop)
    path = tmp_path / "orders.json"
    query = ListQuery(criteria=[Equals("status", "new")])
    app.exports.export("orders", query, EXPORT_COLUMNS, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == [{"order_number": "АС-000002", "status": "new",
                     "total_kop": 0.0, "is_overdue": False}]


def test_unknown_extension_is_rejected(tmp_path):
    with pytest.raises(ValidationError):
        exporter_for(tmp_path / "orders.xlsx")


# ---- імпорт -----------------------------------------------------------------

def _write(tmp_path, text: str, encoding: str = "utf-8") -> str:
    path = tmp_path / "receipt.csv"
    path.write_bytes(text.encode(encoding))
    return str(path)


def test_import_adds_new_and_restocks_existing(app, shop, tmp_path):
    path = _write(tmp_path, (
        "article;name;category;price;quantity;min_qty\n"
        "BRK-1;Колодки передні;Гальмівна система;1300,00;10;\n"
        "BRK-2;Колодки задні;Гальмівна система;1050;4;2\n"))
    events = _record_events(app)
    report = app.parts_import.import_file(path)
    assert (report.added, report.restocked, report.errors) == (1, 1, [])
    part = app.catalog.get_part(shop.part.part_id)
    assert part.stock_qty == 15
    assert part.price == Money.from_uah("1300")
    assert Topic.STOCK in events[0]


def test_import_reports_bad_rows_and_keeps_good_ones(app, shop, tmp_path):
    path = _write(tmp_path, (
        "Артикул;Назва;Категорія;Ціна;Кількість\n"
        "NEW-1;Диск гальмівний;Гальмівна система;1650;2\n"
        "NEW-2;Щось;Невідома категорія;100;1\n"
        "NEW-3;Фільтр;Гальмівна система;дешево;1\n"
        "NEW-4;Фільтр;Гальмівна система;100;0\n"
        "NEW-1;Диск гальмівний;Гальмівна система;1700;3\n"))
    report = app.parts_import.import_file(path)
    assert report.added == 1
    assert len(report.errors) == 3
    assert [error.split(":")[0] for error in report.errors] == \
        ["Рядок 3", "Рядок 4", "Рядок 5"]
    assert "рядку 2" in report.warnings[0]
    rows = app.catalog.find_parts(ListQuery("NEW-1"))
    assert rows[0]["stock_qty"] == 5
    assert rows[0]["price_kop"] == 170_000


def test_import_without_required_columns_changes_nothing(app, shop,
                                                         tmp_path):
    path = _write(tmp_path, "article;name\nBRK-1;Колодки\n")
    with pytest.raises(ValidationError, match="Категорія, Ціна, Кількість"):
        app.parts_import.import_file(path)
    assert _stock(app, shop) == 5


def test_import_reads_windows_1251_and_commas(app, shop, tmp_path):
    path = _write(tmp_path,
                  "article,name,category,price,quantity\n"
                  "BRK-1,Колодки передні,гальмівна система,1250,3\n",
                  encoding="cp1251")
    report = app.parts_import.import_file(path)
    assert report.restocked == 1
    assert _stock(app, shop) == 8


def test_empty_import_file_is_rejected(app, tmp_path):
    with pytest.raises(ValidationError, match="порожній"):
        app.parts_import.import_file(_write(tmp_path, "  \n"))


def test_staff_edit_keeps_phone_unique(app, shop):
    other = Employee("Савчук", "Ігор", "050 111 22 33", date(2021, 3, 1))
    with pytest.raises(ValidationError) as error:
        app.staff.save(other)
    assert error.value.field == "phone"
