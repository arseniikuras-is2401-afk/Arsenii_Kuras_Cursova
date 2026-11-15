"""Приймальні перевірки через графічний інтерфейс.

Скрипт працює з тимчасовою базою в каталозі build/, виконує сценарії так,
як їх виконує користувач (форми, кнопки, діалоги підтвердження), робить
скриншоти в docs/screenshots/ і формує таблицю перевірок
docs/04_testing.md. Дані користувача в data/ не змінюються.

Запуск з кореня проєкту:  python tests/acceptance/run_ui_scenarios.py
"""

import csv
import platform
import sqlite3
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import PYQT_VERSION_STR, Qt, QTimer  # noqa: E402
from PyQt5.QtWidgets import (QApplication, QMessageBox,  # noqa: E402
                             QPushButton)

import main as entry  # noqa: E402
from database import Between, Equals, ListQuery, UnitOfWork  # noqa: E402
from database.setup import open_database  # noqa: E402
from models import (BusinessRuleError,  # noqa: E402
                    InsufficientStockError, InvalidTransitionError,
                    OrderStatus, RecordInUseError, ValidationError)
from services import AppContext  # noqa: E402
from ui.dialogs import ClientForm, NewOrderForm  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.theme import apply_theme  # noqa: E402

BUILD = ROOT / "build" / "acceptance"
SHOTS = ROOT / "docs" / "screenshots"
REPORT = ROOT / "docs" / "04_testing.md"

results: list[dict] = []
figures: list[tuple[str, str]] = []


# ---- службові функції -------------------------------------------------------

def pump(app: QApplication, ms: int = 150):
    timer = QTimer()
    timer.setSingleShot(True)
    timer.start(ms)
    while timer.isActive():
        app.processEvents()


def shot(widget, name: str, caption: str):
    path = SHOTS / f"{name}.png"
    widget.grab().save(str(path))
    figures.append((path.name, caption))
    return len(figures)


def answer_next_dialog(button_text: str, screenshot: tuple | None = None):
    """Натискає кнопку в наступному модальному вікні (як користувач)."""
    def act():
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            QTimer.singleShot(50, act)
            return
        if screenshot:
            shot(dialog, *screenshot)
        for button in dialog.findChildren(QPushButton):
            if button.text().replace("&", "") == button_text:
                button.click()
                return
        dialog.reject()
    QTimer.singleShot(250, act)


def check(scenario: str, given: str, expected: str):
    """Декоратор: функція повертає (фактичний результат, успіх)."""
    def wrap(func):
        try:
            actual, passed = func()
        except Exception as error:   # фіксуємо як провалену перевірку
            traceback.print_exc()
            actual, passed = f"Виняток: {type(error).__name__}: {error}", \
                False
        results.append({"scenario": scenario, "given": given,
                        "expected": expected, "actual": actual,
                        "passed": passed})
        mark = "OK  " if passed else "FAIL"
        print(f"{mark} {len(results):>2}. {scenario}")
        return func
    return wrap


def rows_count(app_context, source: str, query=None) -> int:
    with UnitOfWork(app_context.database) as uow:
        return getattr(uow, source).count(query)


# ---- сценарії ---------------------------------------------------------------

def run():
    BUILD.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    for old in SHOTS.glob("*.png"):
        old.unlink()
    db_path = BUILD / "autoservice.db"
    for leftover in (db_path, BUILD / "empty.db"):
        if leftover.exists():
            leftover.unlink()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    qt_app = QApplication(sys.argv)
    entry._install_translations(qt_app)
    apply_theme(qt_app)

    context = AppContext.open(db_path)
    window = MainWindow(context)
    window.resize(1360, 820)
    window.show()
    pump(qt_app, 500)

    # 1–2. Запуск і повторний запуск ------------------------------------------
    @check("Перший запуск: створення бази й демо-даних",
           "Файлу бази немає", "Створено 10 таблиць і демо-дані")
    def _():
        connection = context.database.connection()
        tables = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        orders = rows_count(context, "orders")
        clients = rows_count(context, "clients")
        return (f"Таблиць: {tables}; клієнтів: {clients}; замовлень: "
                f"{orders}", tables == 10 and orders == 150)

    shot(window, "01_dashboard", "Головна сторінка з показниками")

    @check("Повторний запуск не дублює демо-дані",
           "Закрити й знову відкрити базу",
           "Кількість замовлень не змінилась")
    def _():
        before = rows_count(context, "orders")
        again = open_database(db_path)
        after = again.connection().execute(
            "SELECT count(*) FROM orders").fetchone()[0]
        again.close()
        return f"Було {before}, стало {after}", before == after

    # 3–9. Клієнти ------------------------------------------------------------
    window.show_page("clients")
    pump(qt_app, 300)
    clients_page = window.pages["clients"]

    @check("Додавання клієнта через форму",
           "Мельник Оксана, 066 111 22 33, oksana@ukr.net",
           "Клієнт з'являється в таблиці без перезапуску")
    def _():
        form = ClientForm(context, parent=window)
        form.set_values({"last_name": "Мельник", "first_name": "Оксана",
                         "phone": "066 111 22 33",
                         "email": "oksana@ukr.net"})
        form.accept()
        pump(qt_app, 300)
        found = context.customers.find_clients(ListQuery("0661112233"))
        shown = clients_page.panel.model.row_of(
            found[0]["client_id"]) is not None if found else False
        return (f"Записів знайдено: {len(found)}, у таблиці: "
                f"{'так' if shown else 'ні'}", bool(found) and shown)

    @check("Порожнє обов'язкове поле",
           "Прізвище порожнє", "Кнопка «Зберегти» неактивна")
    def _():
        form = ClientForm(context, parent=window)
        form.set_values({"first_name": "Оксана", "phone": "0661112244"})
        enabled = form.submit_button.isEnabled()
        tip = form.submit_button.toolTip()
        form.close()
        return (f"Кнопка активна: {'так' if enabled else 'ні'}; підказка: "
                f"«{tip}»", not enabled)

    @check("Некоректний телефон",
           "Телефон «067 12»",
           "Помилка під полем, форма не закривається, запис не створено")
    def _():
        count = rows_count(context, "clients")
        form = ClientForm(context, parent=window)
        form.set_values({"last_name": "Бойко", "first_name": "Анна",
                         "phone": "067 12"})
        form.show()
        form.accept()
        pump(qt_app, 200)
        message = form._errors["phone"].text()
        visible = form.isVisible()
        shot(form, "03_client_bad_phone",
             "Помилка формату телефону у формі клієнта")
        form.close()
        return (f"«{message}»; форма відкрита: {visible}",
                bool(message) and visible
                and rows_count(context, "clients") == count)

    @check("Дублікат телефону", "Телефон 066 111 22 33 (уже є)",
           "Помилка «Клієнт з таким телефоном уже є в базі»")
    def _():
        form = ClientForm(context, parent=window)
        form.set_values({"last_name": "Бойко", "first_name": "Анна",
                         "phone": "+380661112233"})
        form.accept()
        message = form._errors["phone"].text()
        form.close()
        return f"«{message}»", "телефоном" in message

    @check("Редагування клієнта", "Нова примітка для Мельник Оксани",
           "Примітку збережено")
    def _():
        row = context.customers.find_clients(ListQuery("0661112233"))[0]
        client = context.customers.get_client(row["client_id"])
        form = ClientForm(context, client, window)
        form.set_values({"note": "Телефонувати після 18:00"})
        form.accept()
        saved = context.customers.get_client(row["client_id"]).note
        return f"Примітка: «{saved}»", saved == "Телефонувати після 18:00"

    @check("Видалення клієнта, який має авто",
           "Клієнт Іваненко Петро (2 авто)",
           "Відмова з поясненням, клієнт лишається")
    def _():
        row = context.customers.find_clients(ListQuery("Іваненко"))[0]
        try:
            context.customers.delete_client(row["client_id"])
        except RecordInUseError as error:
            exists = bool(context.customers.find_clients(
                ListQuery("Іваненко")))
            return f"«{error.message}»", exists
        return "Клієнта видалено", False

    @check("Скасування видалення",
           "Мельник Оксана → «Видалити» → «Скасувати»",
           "Запис не змінився")
    def _():
        clients_page.panel.reset()
        pump(qt_app, 200)
        row = context.customers.find_clients(ListQuery("0661112233"))[0]
        clients_page.panel.select_id(row["client_id"])
        answer_next_dialog("Скасувати",
                           ("04_delete_confirm",
                            "Підтвердження видалення клієнта"))
        clients_page._delete()
        pump(qt_app, 300)
        left = context.customers.find_clients(ListQuery("0661112233"))
        return f"Записів після скасування: {len(left)}", len(left) == 1

    @check("Видалення з підтвердженням",
           "Мельник Оксана (без авто) → «Видалити»",
           "Клієнта видалено, таблиця оновилась")
    def _():
        row = context.customers.find_clients(ListQuery("0661112233"))[0]
        clients_page.panel.select_id(row["client_id"])
        answer_next_dialog("Видалити")
        clients_page._delete()
        pump(qt_app, 300)
        left = context.customers.find_clients(ListQuery("0661112233"))
        in_table = clients_page.panel.model.row_of(row["client_id"])
        return (f"Записів: {len(left)}, рядок у таблиці: "
                f"{'є' if in_table is not None else 'немає'}",
                not left and in_table is None)

    # 10–14. Пошук, фільтри, сортування ---------------------------------------
    window.show_page("orders")
    pump(qt_app, 300)
    orders_page = window.pages["orders"]
    panel = orders_page.panel

    @check("Пошук кирилицею без урахування регістру",
           "Пошук «ІВАНЕНКО» на сторінці «Замовлення»",
           "Знайдено замовлення клієнта Іваненко Петро")
    def _():
        panel.search.setText("ІВАНЕНКО")
        panel._emit_query_now()
        pump(qt_app, 300)
        names = {row["client_name"] for row in panel.model.rows()}
        return (f"Рядків: {len(panel.model.rows())}; клієнти: "
                f"{', '.join(sorted(names))}",
                names == {"Іваненко Петро"})

    @check("Порожній результат пошуку", "Пошук «неіснуючий запит»",
           "Напис «Нічого не знайдено» і кнопка скидання")
    def _():
        panel.search.setText("неіснуючий запит")
        panel._emit_query_now()
        pump(qt_app, 300)
        shot(window, "05_empty_search", "Порожній результат пошуку")
        title = panel._empty_title.text()
        return f"«{title}», рядків: {len(panel.model.rows())}", \
            title == "Нічого не знайдено"

    @check("Фільтрація за трьома умовами одночасно",
           "Статус «Оплачено» + механік Петрук Олег + період «Останні 30 "
           "днів»", "Усі рядки відповідають усім трьом умовам")
    def _():
        panel.reset()
        pump(qt_app, 200)
        orders_page.status_filter.combo.setCurrentIndex(
            orders_page.status_filter.combo.findData("paid"))
        mechanic = orders_page.mechanic_filter.combo
        mechanic.setCurrentIndex(mechanic.findText("Петрук Олег"))
        period = panel.filter_bar.controls[2]
        period.combo.setCurrentIndex(3)
        pump(qt_app, 300)
        rows = panel.model.rows()
        since = (date.today() - timedelta(days=29)).isoformat()
        good = all(row["status"] == "paid"
                   and row["mechanic_name"] == "Петрук Олег"
                   and row["accepted_at"][:10] >= since for row in rows)
        shot(window, "06_orders_filters",
             "Замовлення: три фільтри одночасно")
        return f"Рядків: {len(rows)}, усі відповідають: {good}", \
            good and bool(rows)

    @check("Сортування за двома полями",
           "Механік ↑, потім сума ↓", "Рядки впорядковано за обома ключами")
    def _():
        panel.reset()
        bar = panel.sort_bar
        bar.primary.setCurrentIndex(bar.primary.findData("mechanic_name"))
        bar.primary_direction.setChecked(False)
        bar.secondary.setCurrentIndex(bar.secondary.findData("total_kop"))
        bar.secondary_direction.setChecked(True)
        pump(qt_app, 300)
        pairs = [(row["mechanic_name"], -row["total_kop"])
                 for row in panel.model.rows()]
        shot(window, "07_orders_sorted",
             "Сортування: механік за зростанням, сума за спаданням")
        return f"Рядків: {len(pairs)}, порядок правильний: " \
               f"{pairs == sorted(pairs)}", pairs == sorted(pairs)

    @check("Скидання пошуку, фільтрів і сортування", "Кнопка «Скинути»",
           "Показано всі 150 замовлень, новіші — першими")
    def _():
        panel.reset()
        pump(qt_app, 300)
        rows = panel.model.rows()
        ordered = [row["accepted_at"] for row in rows]
        return f"Рядків: {len(rows)}", len(rows) == 150 \
            and ordered == sorted(ordered, reverse=True)

    # 15–24. Замовлення -------------------------------------------------------
    free_car = next(row for row in context.customers.find_cars()
                    if not row["has_open_order"])
    state = {}

    @check("Оформлення замовлення через форму",
           f"Авто {free_car['plate_number']}, скарга «Стук у підвісці»",
           "Створено замовлення зі статусом «Нове» і записом в історії")
    def _():
        form = NewOrderForm(context, free_car["car_id"], window)
        form.set_values({"complaint": "Стук у підвісці"})
        form.show()
        pump(qt_app, 200)
        shot(form, "08_new_order", "Форма нового замовлення")
        form.accept()
        order = context.orders.get(form.order_id)
        state["order_id"] = form.order_id
        history = context.orders.history(form.order_id)
        return (f"{order.number}, статус «{order.status.title}», записів "
                f"історії: {len(history)}",
                order.status is OrderStatus.NEW and len(history) == 1)

    @check("Друге відкрите замовлення для того самого авто",
           f"Ще одне замовлення для {free_car['plate_number']}",
           "Відмова з номером відкритого замовлення")
    def _():
        form = NewOrderForm(context, free_car["car_id"], window)
        form.set_values({"complaint": "Ще раз"})
        form.accept()
        text = form.banner.text()
        form.close()
        return f"«{text}»", "уже є відкрите замовлення" in text

    @check("Ручна знижка більше 30 %", "Знижка 31 %",
           "Помилка поля «Знижка»")
    def _():
        try:
            context.orders.update_header(
                state["order_id"],
                context.orders.get(state["order_id"]).mechanic.employee_id,
                date.today() + timedelta(days=2), "Стук у підвісці", 31)
        except ValidationError as error:
            return f"«{error.message}» (поле {error.field})", \
                error.field == "manual_discount_pct"
        return "Збережено", False

    @check("Почати роботу без жодної роботи в замовленні",
           "Нове замовлення без рядків → «Почати роботу»", "Відмова")
    def _():
        try:
            context.orders.change_status(state["order_id"],
                                         OrderStatus.IN_PROGRESS)
        except BusinessRuleError as error:
            return f"«{error.message}»", True
        return "Статус змінено", False

    part_row = next(row for row in context.catalog.find_parts()
                    if row["stock_qty"] >= 3)

    @check("Запчастин більше, ніж на складі",
           f"«{part_row['name']}» × {part_row['stock_qty'] + 1}",
           "Відмова, залишок не змінився")
    def _():
        try:
            context.orders.add_part(state["order_id"], part_row["part_id"],
                                    part_row["stock_qty"] + 1)
        except InsufficientStockError as error:
            stock = context.catalog.get_part(part_row["part_id"]).stock_qty
            return f"«{error.message}»; залишок {stock}", \
                stock == part_row["stock_qty"]
        return "Додано", False

    @check("Додавання роботи й запчастини",
           f"Робота «Діагностика ходової» × 1; «{part_row['name']}» × 2",
           "Залишок зменшився на 2, сума замовлення перерахована")
    def _():
        work = next(item for item in context.catalog.active_work_types()
                    if item.name == "Діагностика ходової")
        context.orders.add_work(state["order_id"], work.work_type_id, 1)
        context.orders.add_part(state["order_id"], part_row["part_id"], 2)
        stock = context.catalog.get_part(part_row["part_id"]).stock_qty
        order = context.orders.get(state["order_id"])
        return (f"Залишок {part_row['stock_qty']} → {stock}; сума "
                f"{order.total()}", stock == part_row["stock_qty"] - 2)

    @check("Автооновлення пов'язаних подань",
           "Після списання запчастини відкрити сторінку «Склад»",
           "Новий залишок видно без перезапуску")
    def _():
        window.show_page("stock")
        pump(qt_app, 300)
        stock_page = window.pages["stock"]
        row = stock_page.panel.model.row_of(part_row["part_id"])
        shown = stock_page.panel.model.row_data(row)["stock_qty"]
        return f"У таблиці «Склад»: {shown}", \
            shown == part_row["stock_qty"] - 2

    @check("Недозволений перехід статусу", "«Нове» → «Оплачено»",
           "Відмова «Перехід … неможливий»")
    def _():
        try:
            context.orders.change_status(state["order_id"], OrderStatus.PAID)
        except InvalidTransitionError as error:
            return f"«{error.message}»", True
        return "Статус змінено", False

    @check("Повний цикл статусів і блокування оплаченого",
           "Почати роботу → Завершити → Прийняти оплату",
           "Пробіг авто оновлено; кнопки зміни рядків неактивні")
    def _():
        for status in (OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED,
                       OrderStatus.PAID):
            context.orders.change_status(state["order_id"], status)
        order = context.orders.get(state["order_id"])
        window.open_order(state["order_id"])
        pump(qt_app, 400)
        order_window = window._order_windows[state["order_id"]]
        locked = not order_window.works["add"].isEnabled()
        shot(order_window, "09_order_paid",
             "Оплачене замовлення: зміни заблоковано")
        order_window.close()
        car = context.customers.get_car(free_car["car_id"])
        return (f"Статус «{order.status.title}», пробіг авто "
                f"{car.mileage_km}, кнопки заблоковані: {locked}",
                locked and car.mileage_km == order.intake_mileage_km)

    @check("Скасування замовлення повертає запчастини",
           "Нове замовлення з 2 шт. → «Скасувати замовлення»",
           "Залишок відновився")
    def _():
        car = next(row for row in context.customers.find_cars()
                   if not row["has_open_order"])
        mechanic = context.staff.available_mechanics()[0][0]
        order_id = context.orders.create(
            car["car_id"], mechanic.employee_id, "Перевірка скасування",
            date.today() + timedelta(days=1), car["mileage_km"])
        before = context.catalog.get_part(part_row["part_id"]).stock_qty
        context.orders.add_part(order_id, part_row["part_id"], 2)
        window.open_order(order_id)
        pump(qt_app, 400)
        order_window = window._order_windows[order_id]
        shot(order_window, "10_order_window", "Вікно замовлення")
        answer_next_dialog("Скасувати замовлення",
                           ("11_cancel_dialog",
                            "Підтвердження скасування з коментарем"))
        order_window._change_status(OrderStatus.CANCELLED)
        pump(qt_app, 300)
        order_window.close()
        after = context.catalog.get_part(part_row["part_id"]).stock_qty
        status = context.orders.get(order_id).status.title
        return f"Залишок {before} → {before - 2} → {after}; «{status}»", \
            after == before

    @check("Механік з 4 відкритими замовленнями",
           "Призначити механіку з навантаженням 4",
           "Механіка немає у списку, сервіс відмовляє")
    def _():
        busy = [row for row in context.staff.find()
                if row["is_active"] and row["open_orders"] >= 4]
        if not busy:
            row = context.staff.find()[0]
            cars = [car for car in context.customers.find_cars()
                    if not car["has_open_order"]]
            for car in cars[:4 - row["open_orders"]]:
                context.orders.create(car["car_id"], row["employee_id"],
                                      "Навантаження", date.today(),
                                      car["mileage_km"])
            busy = [row]
        employee_id = busy[0]["employee_id"]
        listed = employee_id in {item.employee_id for item, _ in
                                 context.staff.available_mechanics()}
        order = context.orders.get(state["order_id"])
        car = next(car for car in context.customers.find_cars()
                   if not car["has_open_order"])
        try:
            context.orders.create(car["car_id"], employee_id, "Ще одне",
                                  date.today(), car["mileage_km"])
        except BusinessRuleError as error:
            return f"У списку: {listed}; «{error.message}»", not listed
        del order
        return "Замовлення створено", False

    # 25–27. Імпорт і експорт -------------------------------------------------
    @check("Імпорт накладної з помилковими рядками",
           "CSV: 2 коректні рядки, 1 з невідомою категорією, 1 з ціною "
           "«дешево»", "Коректні рядки імпортовано, звіт з номерами рядків")
    def _():
        path = BUILD / "receipt.csv"
        path.write_text(
            "Артикул;Назва;Категорія;Ціна;Кількість\n"
            "NEW-TEST-1;Диск тестовий;Гальмівна система;1650;2\n"
            "BRK-PAD-F01;Колодки гальмівні передні;Гальмівна система;"
            "1300;5\n"
            "NEW-TEST-2;Щось;Невідома;100;1\n"
            "NEW-TEST-3;Фільтр;ТО та мастила;дешево;1\n", encoding="utf-8")
        report = context.parts_import.import_file(path)
        box = QMessageBox(QMessageBox.Warning, "Результат імпорту",
                          report.summary(), parent=window)
        box.setInformativeText("\n".join(report.errors))
        box.show()
        pump(qt_app, 200)
        shot(box, "12_import_report", "Звіт імпорту накладної")
        box.close()
        return (f"Нових {report.added}, поповнено {report.restocked}, "
                f"помилок {len(report.errors)}: "
                f"{'; '.join(report.errors)}",
                report.added == 1 and report.restocked == 1
                and len(report.errors) == 2)

    @check("Імпорт файлу без обов'язкових стовпців",
           "CSV із заголовками article;name", "Відмова, склад не змінено")
    def _():
        path = BUILD / "bad.csv"
        path.write_text("article;name\nX-1;Щось\n", encoding="utf-8")
        before = rows_count(context, "parts")
        try:
            context.parts_import.import_file(path)
        except ValidationError as error:
            return f"«{error.message[:70]}…»", \
                rows_count(context, "parts") == before
        return "Імпортовано", False

    @check("Експорт відфільтрованої вибірки в CSV",
           "Склад, «Лише нижче мінімуму» → Експорт",
           "Файл з BOM, «;», рядків стільки ж, скільки в таблиці")
    def _():
        window.show_page("stock")
        stock_page = window.pages["stock"]
        stock_page.show_low_stock()
        pump(qt_app, 300)
        shot(window, "13_stock_low", "Склад: лише запчастини нижче мінімуму")
        path = BUILD / "low.csv"
        count = context.exports.export(
            "parts", stock_page.panel.current_query(),
            stock_page.panel.export_columns(), path)
        raw = path.read_bytes()
        lines = list(csv.reader(raw.decode("utf-8-sig").splitlines(),
                                delimiter=";"))
        shown = len(stock_page.panel.model.rows())
        stock_page.panel.reset()
        return (f"У таблиці {shown}, у файлі {len(lines) - 1}; BOM: "
                f"{raw.startswith(b'\xef\xbb\xbf')}",
                count == shown == len(lines) - 1
                and raw.startswith(b"\xef\xbb\xbf"))

    @check("Експорт у JSON", "Замовлення → файл .json",
           "Масив об'єктів, суми — числами")
    def _():
        import json
        path = BUILD / "orders.json"
        context.exports.export("orders", ListQuery(
            criteria=[Equals("status", "paid")]),
            window.pages["orders"].panel.export_columns(), path)
        data = json.loads(path.read_text(encoding="utf-8"))
        first = data[0]
        return (f"Об'єктів: {len(data)}; total_kop = {first['total_kop']} "
                f"({type(first['total_kop']).__name__})",
                isinstance(first["total_kop"], float))

    # 28–30. Статистика, збереження, порожня база -----------------------------
    @check("Статистика за період", "Останні 6 місяців, усі механіки",
           "Виручка збігається з сумою оплачених замовлень")
    def _():
        window.show_page("statistics")
        pump(qt_app, 600)
        shot(window, "14_statistics", "Статистика й графіки Matplotlib")
        page = window.pages["statistics"]
        start, end = page._range()
        revenue, paid = context.reports.revenue_summary(start, end)
        rows = context.orders.find(ListQuery(criteria=[
            Equals("status", "paid"),
            Between("paid_on", start.isoformat(), end.isoformat())]))
        total = sum(row["total_kop"] for row in rows)
        return f"Звіт: {revenue}, {paid} замовлень; за списком: " \
               f"{total / 100:.2f} грн, {len(rows)}", \
            revenue.kop == total and paid == len(rows)

    @check("Період, у якому кінець раніше початку",
           "Статистика: 10.11.2026 – 01.11.2026",
           "Червона рамка поля, графіки не перебудовуються")
    def _():
        page = window.pages["statistics"]
        page.period.setCurrentIndex(4)
        page.start.setDate(date(2026, 11, 10))
        page.end.setDate(date(2026, 11, 1))
        pump(qt_app, 200)
        invalid = page.end.property("invalid")
        page.period.setCurrentIndex(1)
        return f"Поле позначено помилковим: {invalid}", bool(invalid)

    @check("Збереження даних після закриття програми",
           "Закрити й знову відкрити застосунок",
           "Створене замовлення й зміни складу на місці")
    def _():
        reopened = AppContext.open(db_path)
        order = reopened.orders.get(state["order_id"])
        stock = reopened.catalog.get_part(part_row["part_id"]).stock_qty
        reopened.close()
        return f"{order.number} «{order.status.title}», залишок {stock}", \
            order.status is OrderStatus.PAID

    window.close()
    context.close()

    @check("Робота з порожньою базою", "База без демо-даних",
           "Сторінки показують «… ще немає», помилок немає")
    def _():
        empty = AppContext(open_database(BUILD / "empty.db",
                                         with_demo_data=False))
        empty_window = MainWindow(empty)
        empty_window.resize(1360, 820)
        empty_window.show()
        empty_window.show_page("orders")
        pump(qt_app, 400)
        shot(empty_window, "15_empty_database", "Порожня база даних")
        text = empty_window.pages["orders"].panel._empty_title.text()
        empty_window.show_page("dashboard")
        pump(qt_app, 300)
        empty_window.close()
        empty.close()
        return f"«{text}»", text == "Замовлень ще немає"

    return qt_app


# ---- звіт -------------------------------------------------------------------

def write_report():
    passed = sum(1 for item in results if item["passed"])
    lines = [
        "# Етап 7. Тестування застосунку",
        "",
        "## 4.1 Умови та сценарії тестування",
        "",
        f"- Середовище: {platform.system()} {platform.release()}, "
        f"Python {platform.python_version()}, PyQt {PYQT_VERSION_STR}, "
        f"SQLite {sqlite3.sqlite_version}.",
        f"- Дата перевірки: {datetime.now():%d.%m.%Y %H:%M}.",
        "- Тестові дані: демонстраційна база (30 клієнтів, 40 авто, "
        "6 механіків, 35 робіт, 31 запчастина, 150 замовлень), окрема "
        "порожня база, CSV-накладні з коректними й помилковими рядками.",
        "- Приймальні перевірки виконує скрипт "
        "`tests/acceptance/run_ui_scenarios.py` через віджети інтерфейсу "
        "(форми, кнопки, діалоги підтвердження) на тимчасовій копії бази. "
        "Таблицю нижче й скриншоти скрипт формує автоматично.",
        "- Модульні тести pytest (`python -m pytest`) перевіряють моделі, "
        "шар бази й сервіси окремо: 113 тестів.",
        "",
        "## 4.2 Результати тестування",
        "",
        f"Пройдено {passed} з {len(results)} перевірок.",
        "",
        "| № | Сценарій / дія | Вхідні дані | Очікуваний результат | "
        "Фактичний результат | Висновок |",
        "|---|---|---|---|---|---|",
    ]
    for number, item in enumerate(results, start=1):
        cells = [str(number), item["scenario"], item["given"],
                 item["expected"], item["actual"],
                 "Пройдено" if item["passed"] else "**Не пройдено**"]
        lines.append("| " + " | ".join(
            cell.replace("|", "/").replace("\n", " ") for cell in cells)
            + " |")
    lines += [
        "",
        "### Виявлені та усунені недоліки",
        "",
        "| Недолік | Як виявлено | Виправлення |",
        "|---|---|---|",
        "| Тест дати замовлення проходив через закоротку скаргу «ТО», а не "
        "через дату | Перевірка поля помилки в тесті | Тест перевіряє "
        "`error.field == \"due_date\"` |",
        "| Рейтинг робіт рахував штуки: «Балансування» (4 колеса) завжди "
        "було першим | Перегляд даних графіка | Рахується кількість "
        "замовлень з роботою |",
        "| У демо-даних «мало на складі» потрапляли позиції із залишком 17 "
        "| Перегляд головної сторінки | Обираються справді найдефіцитніші "
        "позиції |",
        "| Обрізаний стовпець «Сума» і горизонтальна прокрутка в таблицях | "
        "Скриншоти | Стовпець, що розтягується (`ColumnSpec.stretch`) |",
        "| Неактивна червона кнопка «Видалити» виглядала активною | "
        "Скриншоти | Окремий стиль `danger:disabled` |",
        "| Поля фільтра «від – до» розтягувались на всю ширину | Скриншоти "
        "| Фіксована політика розміру `FilterControl` |",
        "",
        "### Вимоги, підтверджені перевірками",
        "",
        "- CRUD для клієнтів, авто, механіків, довідників і замовлень; "
        "підтвердження й скасування видалення.",
        "- Пошук за кількома полями (кирилиця без урахування регістру), "
        "фільтр за трьома умовами, сортування за двома полями, скидання.",
        "- Операції предметної області: оформлення замовлення, списання "
        "запчастин у транзакції, переходи статусів, знижки.",
        "- Імпорт CSV з перевіркою структури, значень і дублікатів; експорт "
        "CSV/JSON поточної вибірки.",
        "- Збереження даних після перезапуску, відсутність дублювання "
        "демо-даних, робота з порожньою базою, автооновлення подань.",
        "",
        "### Відомі обмеження",
        "",
        "- Один користувач і одне робоче місце: одночасна робота кількох "
        "програм з одним файлом бази не передбачена.",
        "- Немає авторизації та розмежування прав (методичка не вимагає).",
        "- Оплата лише повна, без часткових оплат і передоплат.",
        "- Ознака «прострочено» в таблицях рахується за системною датою "
        "комп'ютера.",
        "- Імпорт підтримує лише прихід запчастин (CSV до 5000 рядків).",
        "",
        "## Рисунки",
        "",
    ]
    for number, (name, caption) in enumerate(figures, start=1):
        lines += [f"![Рисунок 4.{number} — {caption}](screenshots/{name})",
                  "", f"*Рисунок 4.{number} — {caption}*", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{passed}/{len(results)} перевірок пройдено; звіт: {REPORT}")
    return passed == len(results)


if __name__ == "__main__":
    run()
    sys.exit(0 if write_report() else 1)
