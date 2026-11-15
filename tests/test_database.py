"""Тести шару бази даних: схема, транзакції, обмеження, вибірки, демо-дані."""

import sqlite3
from datetime import date, datetime, timedelta

import pytest

from database import (Between, Database, Equals, IsTrue, ListQuery,
                      SchemaManager, SortKey, UnitOfWork)
from database.demo_seeder import DemoSeeder
from database.setup import open_database
from models import (BusinessRuleError, Client, Money, NotFoundError, Order,
                    OrderStatus, RecordInUseError, ValidationError)

NOW = datetime(2026, 11, 14, 12, 0)
FIXED_NOW = NOW  # та сама дата, що й у фікстурі demo_database


# ---- схема й запуск ---------------------------------------------------------

def test_new_database_gets_schema_version(database):
    connection = database.connection()
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert not SchemaManager().needs_creation(connection)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_reopening_keeps_data_and_does_not_duplicate_demo(tmp_path):
    path = tmp_path / "autoservice.db"
    database = open_database(path)
    first = database.connection().execute(
        "SELECT count(*) FROM orders").fetchone()[0]
    database.close()
    database = open_database(path)
    second = database.connection().execute(
        "SELECT count(*) FROM orders").fetchone()[0]
    database.close()
    assert first > 0
    assert first == second


def test_failed_seeding_leaves_empty_file(tmp_path, monkeypatch):
    def broken_seed(self, uow):
        raise RuntimeError("перервано")

    monkeypatch.setattr(DemoSeeder, "seed", broken_seed)
    path = tmp_path / "broken.db"
    with pytest.raises(RuntimeError):
        open_database(path)
    database = Database(path)
    connection = database.connection()
    assert SchemaManager().needs_creation(connection)
    tables = connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()
    assert tables[0] == 0
    database.close()


# ---- транзакції й обмеження -------------------------------------------------

def test_exception_rolls_back_whole_unit(database):
    with pytest.raises(RuntimeError):
        with UnitOfWork(database) as uow:
            uow.clients.insert(Client("Мельник", "Оксана", "0661112233"))
            raise RuntimeError("щось пішло не так")
    with UnitOfWork(database) as uow:
        assert uow.clients.count() == 0


def test_nested_units_are_forbidden(database):
    with UnitOfWork(database):
        with pytest.raises(RuntimeError):
            with UnitOfWork(database):
                pass


def test_duplicate_phone_is_translated(database, stored):
    with pytest.raises(ValidationError) as error:
        with UnitOfWork(database) as uow:
            uow.clients.insert(Client("Мельник", "Оксана", "067 123 45 67"))
    assert error.value.field == "phone"
    assert "телефоном" in error.value.message


def test_client_with_car_cannot_be_deleted(database, stored):
    client_id = stored["client"].client_id
    with UnitOfWork(database) as uow:
        assert uow.clients.usages(client_id) == ["автомобілів: 1"]
    with pytest.raises(RecordInUseError):
        with UnitOfWork(database) as uow:
            uow.clients.delete(client_id)
    with UnitOfWork(database) as uow:
        assert uow.clients.get(client_id).last_name == "Іваненко"


def test_negative_stock_is_blocked_by_check(database, stored):
    with pytest.raises(BusinessRuleError):
        with UnitOfWork(database):
            database.connection().execute(
                "UPDATE parts SET stock_qty = -1 WHERE part_id = ?",
                (stored["part"].part_id,))


def test_deleting_order_cascades_to_lines(database, stored):
    order_id = _save_order(database, stored)
    with UnitOfWork(database) as uow:
        uow.orders.delete(order_id)
    connection = database.connection()
    for table in ("order_works", "order_parts", "order_status_log"):
        count = connection.execute(
            f"SELECT count(*) FROM {table} WHERE order_id = ?",
            (order_id,)).fetchone()[0]
        assert count == 0


def test_missing_record_raises_not_found(database):
    with UnitOfWork(database) as uow:
        with pytest.raises(NotFoundError):
            uow.cars.get(999)


# ---- збереження замовлення --------------------------------------------------

def _save_order(database, stored) -> int:
    with UnitOfWork(database) as uow:
        car = uow.cars.get(stored["car"].car_id)
        mechanic = uow.employees.get(stored["mechanic"].employee_id)
        order = Order.open_new(car, mechanic, "Скрип гальм",
                               date.today() + timedelta(days=1), 151_000,
                               manual_discount_pct=10)
        uow.orders.insert(order)
        uow.orders.log_status(order.order_id, None, OrderStatus.NEW, NOW)
        part = uow.parts.get(stored["part"].part_id)
        for line in (order.add_work(uow.work_types.get(1), 2),
                     order.add_part(part, 2), order.add_part(part, 1)):
            uow.orders.save_line(order, line)
        uow.parts.update_stock(part)
        return order.order_id


def test_order_round_trip_keeps_lines_and_total(database, stored):
    order_id = _save_order(database, stored)
    with UnitOfWork(database) as uow:
        order = uow.orders.get(order_id)
        row = uow.orders.find(ListQuery(criteria=[Equals("order_id",
                                                          order_id)]))[0]
        stock = uow.parts.get(stored["part"].part_id).stock_qty
    assert len(order.work_lines()) == 1
    assert order.part_lines()[0].quantity == 3
    assert stock == 2
    # 900 + 3750 = 4650; знижка 10 % → 4185
    assert order.total() == Money.from_uah("4185")
    assert row["total_kop"] == order.total().kop
    assert row["order_number"] == order.number


def test_status_change_is_saved_with_history(database, stored):
    order_id = _save_order(database, stored)
    with UnitOfWork(database) as uow:
        order = uow.orders.get(order_id)
        order.change_status(OrderStatus.IN_PROGRESS, NOW)
        uow.orders.update_status(order)
        uow.orders.log_status(order_id, OrderStatus.NEW,
                              OrderStatus.IN_PROGRESS, NOW, "Почали")
    with UnitOfWork(database) as uow:
        assert uow.orders.get(order_id).status is OrderStatus.IN_PROGRESS
        history = uow.orders.status_history(order_id)
    assert [row["new_status"] for row in history] == ["new", "in_progress"]
    assert history[-1]["comment"] == "Почали"


# ---- вибірки ----------------------------------------------------------------

def test_search_ignores_case_of_cyrillic(demo_database):
    with UnitOfWork(demo_database) as uow:
        upper = uow.clients.find(ListQuery("ІВАНЕНКО"))
        lower = uow.clients.find(ListQuery("іваненко"))
    assert len(upper) == 1
    assert [row["client_id"] for row in upper] == \
        [row["client_id"] for row in lower]


def test_percent_sign_is_searched_literally(demo_database):
    with UnitOfWork(demo_database) as uow:
        assert uow.clients.find(ListQuery("%")) == []


def test_injection_in_search_is_harmless(demo_database):
    with UnitOfWork(demo_database) as uow:
        assert uow.clients.find(
            ListQuery("'; DROP TABLE clients; --")) == []
        assert uow.clients.count() == 30


def test_unknown_field_is_rejected(demo_database):
    with UnitOfWork(demo_database) as uow:
        with pytest.raises(ValueError):
            uow.orders.find(ListQuery(sort_keys=[SortKey("1; DROP")]))
        with pytest.raises(ValueError):
            uow.orders.find(ListQuery(criteria=[Equals("password", 1)]))


def test_three_filters_together(demo_database):
    criteria = [Equals("status", "paid"),
                Between("total_kop", 100_000, 500_000),
                Between("accepted_on", "2026-08-01", "2026-10-31")]
    with UnitOfWork(demo_database) as uow:
        rows = uow.orders.find(ListQuery(criteria=criteria))
    assert rows
    for row in rows:
        assert row["status"] == "paid"
        assert 100_000 <= row["total_kop"] <= 500_000
        assert "2026-08-01" <= row["accepted_at"][:10] <= "2026-10-31"


def test_sorting_by_two_fields(demo_database):
    keys = [SortKey("mechanic_name"), SortKey("total_kop", descending=True)]
    with UnitOfWork(demo_database) as uow:
        rows = uow.orders.find(ListQuery(sort_keys=keys))
    pairs = [(row["mechanic_name"], -row["total_kop"]) for row in rows]
    assert pairs == sorted(pairs)


def test_low_stock_flag(demo_database):
    with UnitOfWork(demo_database) as uow:
        rows = uow.parts.find(ListQuery(criteria=[IsTrue("is_low")]))
    assert rows
    assert all(row["stock_qty"] < row["min_qty"] for row in rows)


# ---- демо-дані --------------------------------------------------------------

def test_view_totals_match_python_totals(demo_database):
    with UnitOfWork(demo_database) as uow:
        rows = uow.orders.find()
        for row in rows:
            order = uow.orders.get(row["order_id"])
            assert row["total_kop"] == order.total().kop
            assert row["discount_kop"] == order.discount_amount().kop


def test_demo_data_respects_business_rules(demo_database):
    connection = demo_database.connection()
    open_status = "status IN ('new', 'in_progress')"
    assert connection.execute(
        f"SELECT max(n) FROM (SELECT count(*) n FROM orders "
        f"WHERE {open_status} GROUP BY car_id)").fetchone()[0] == 1
    assert connection.execute(
        f"SELECT max(n) FROM (SELECT count(*) n FROM orders "
        f"WHERE {open_status} GROUP BY employee_id)").fetchone()[0] <= 4
    assert connection.execute(
        f"SELECT count(*) FROM orders o JOIN employees e "
        f"USING (employee_id) WHERE e.is_active = 0 AND o.{open_status}"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT count(*) FROM orders WHERE paid_at < completed_at"
    ).fetchone()[0] == 0
    first_logs = connection.execute(
        "SELECT new_status FROM order_status_log l WHERE log_id = "
        "(SELECT min(log_id) FROM order_status_log WHERE order_id = "
        "l.order_id)").fetchall()
    assert {row[0] for row in first_logs} == {"new"}


def test_demo_data_is_reproducible():
    totals = []
    for _ in range(2):
        database = Database(":memory:")
        with UnitOfWork(database) as uow:
            SchemaManager().create(database.connection())
            DemoSeeder(now=FIXED_NOW).seed(uow)
            totals.append([(row["plate_number"], row["total_kop"])
                           for row in uow.orders.find()])
        database.close()
    assert totals[0] == totals[1]


def test_dashboard_numbers_are_consistent(demo_database):
    with UnitOfWork(demo_database) as uow:
        summary = uow.reports.dashboard(FIXED_NOW.date())
        open_count = uow.orders.count(ListQuery(criteria=[IsTrue("is_open")]))
    assert summary["open_orders"] == open_count
    assert summary["overdue"] <= summary["open_orders"]
    assert summary["low_stock"] > 0


def test_integrity_error_class_is_not_leaked(database, stored):
    with pytest.raises(ValidationError):
        with UnitOfWork(database):
            database.connection().execute(
                "INSERT INTO cars (client_id, make, model, production_year, "
                "plate_number) VALUES (?, 'Kia', 'Rio', 2020, 'AT1234BC')",
                (stored["client"].client_id,))
    assert not issubclass(ValidationError, sqlite3.Error)
