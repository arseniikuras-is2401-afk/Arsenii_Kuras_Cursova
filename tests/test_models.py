"""Тести класів предметної області."""

from datetime import date, datetime, timedelta

import pytest

from models import (BusinessRuleError, Car, Client, Employee,
                    InsufficientStockError, InvalidTransitionError, Money,
                    Order, OrderStatus, ValidationError)
from models.validators import (normalize_email, normalize_phone,
                               normalize_plate, normalize_vin)

NOW = datetime(2026, 11, 14, 12, 0)


# ---- гроші -----------------------------------------------------------------

@pytest.mark.parametrize("text, kop", [
    ("1250", 125_000), ("1 250,5", 125_050), ("1250.50 грн", 125_050),
    ("0,01", 1), ("0", 0),
])
def test_money_parses_user_input(text, kop):
    assert Money.from_text(text).kop == kop


@pytest.mark.parametrize("text", ["", "абв", "12,345", "1.2.3", "--5"])
def test_money_rejects_bad_input(text):
    with pytest.raises(ValidationError):
        Money.from_text(text)


def test_money_percent_rounds_half_up():
    assert Money(33_333).percent(5).kop == 1_667     # 1666,65 → 1667
    assert Money(10).percent(5).kop == 1             # 0,5 → 1
    assert Money(9).percent(5).kop == 0              # 0,45 → 0


def test_money_formats_with_thousands_separator():
    assert Money(123_450).to_text() == "1 234,50 грн"
    assert Money(-500).to_text(with_currency=False) == "−5,00"


# ---- нормалізація -----------------------------------------------------------

@pytest.mark.parametrize("raw", ["+38 (067) 123-45-67", "380671234567",
                                 "067 123 45 67", "0671234567"])
def test_phone_is_normalized(raw):
    assert normalize_phone(raw) == "0671234567"


@pytest.mark.parametrize("raw", ["12345", "1671234567", "067123456789", ""])
def test_bad_phone_is_rejected(raw):
    with pytest.raises(ValidationError) as error:
        normalize_phone(raw)
    assert error.value.field == "phone"


def test_plate_with_cyrillic_letters_becomes_latin():
    assert normalize_plate("ат 1234 вс") == "AT1234BC"


@pytest.mark.parametrize("raw", ["AT123BC", "1234ATBC", "AT1234B"])
def test_bad_plate_is_rejected(raw):
    with pytest.raises(ValidationError):
        normalize_plate(raw)


def test_vin_rejects_forbidden_letters():
    assert normalize_vin("wvwzzz1jz3w386752") == "WVWZZZ1JZ3W386752"
    assert normalize_vin("  ") is None
    with pytest.raises(ValidationError):
        normalize_vin("WVWZZZ1JZ3W38675O")   # літера O заборонена


def test_empty_email_becomes_none():
    assert normalize_email("  ") is None
    assert normalize_email("Petro@UKR.net") == "petro@ukr.net"
    with pytest.raises(ValidationError):
        normalize_email("petro@ukr")


# ---- люди й авто ------------------------------------------------------------

def test_name_with_digits_is_rejected():
    with pytest.raises(ValidationError) as error:
        Client("Іван3нко", "Петро", "0671234567")
    assert error.value.field == "last_name"


def test_client_display_name_contains_phone(client):
    assert client.display_name() == "Іваненко Петро · 067 123 45 67"


def test_employee_cannot_be_hired_in_future(category):
    with pytest.raises(ValidationError):
        Employee("Петрук", "Олег", "0501112233",
                 date.today() + timedelta(days=1), category)


def test_mileage_cannot_decrease(car):
    car.register_mileage(160_000)
    with pytest.raises(ValidationError):
        car.register_mileage(155_000)
    assert car.mileage_km == 160_000


def test_production_year_in_future_is_rejected(client):
    with pytest.raises(ValidationError):
        Car(client, "Kia", "Rio", date.today().year + 2, "AT0001AA")


# ---- склад ------------------------------------------------------------------

def test_part_cannot_go_below_zero(brake_pads):
    with pytest.raises(InsufficientStockError):
        brake_pads.take(6)
    assert brake_pads.stock_qty == 5
    brake_pads.take(4)
    assert brake_pads.is_low_stock()
    brake_pads.put_back(4)
    assert brake_pads.stock_qty == 5


# ---- створення замовлення ---------------------------------------------------

def test_intake_mileage_below_last_known_is_rejected(car, mechanic):
    with pytest.raises(ValidationError) as error:
        Order.open_new(car, mechanic, "Планове ТО", date.today(), 149_999)
    assert error.value.field == "intake_mileage_km"


def test_inactive_mechanic_cannot_take_new_order(car, mechanic):
    mechanic.is_active = False
    with pytest.raises(BusinessRuleError):
        Order.open_new(car, mechanic, "Планове ТО", date.today(), 150_000)


def test_due_date_limits(car, mechanic):
    accepted = datetime(2026, 11, 10, 9, 0)
    with pytest.raises(ValidationError):
        Order.open_new(car, mechanic, "Планове ТО", date(2026, 11, 9), 150_000,
                       accepted_at=accepted)
    with pytest.raises(ValidationError):
        Order.open_new(car, mechanic, "Планове ТО", date(2027, 1, 10), 150_000,
                       accepted_at=accepted)


# ---- рядки й суми -----------------------------------------------------------

def test_same_part_is_merged_into_one_line(new_order, brake_pads):
    new_order.add_part(brake_pads, 2)
    line = new_order.add_part(brake_pads, 1)
    assert line.quantity == 3
    assert len(new_order.part_lines()) == 1
    assert brake_pads.stock_qty == 2


def test_too_many_parts_leave_stock_and_order_unchanged(new_order,
                                                         brake_pads):
    with pytest.raises(InsufficientStockError):
        new_order.add_part(brake_pads, 9)
    assert brake_pads.stock_qty == 5
    assert new_order.lines() == ()


def test_removing_part_line_returns_stock(new_order, brake_pads):
    line = new_order.add_part(brake_pads, 2)
    new_order.remove_line(line)
    assert brake_pads.stock_qty == 5
    assert new_order.lines() == ()


def test_price_is_fixed_when_line_is_added(new_order, brake_job):
    line = new_order.add_work(brake_job, 1)
    brake_job.price = Money.from_uah("999")
    assert line.unit_price == Money.from_uah("450")


def test_inactive_work_type_cannot_be_added(new_order, brake_job):
    brake_job.is_active = False
    with pytest.raises(BusinessRuleError):
        new_order.add_work(brake_job, 1)


def test_bigger_discount_wins_and_loyalty_skips_parts(car, mechanic,
                                                      brake_job, brake_pads):
    order = Order.open_new(car, mechanic, "Гальма", date.today(), 150_000,
                           manual_discount_pct=0, loyalty_discount_pct=5)
    order.add_work(brake_job, 2)        # 900 грн
    order.add_part(brake_pads, 2)       # 2500 грн
    assert order.discount_amount() == Money.from_uah("45")   # 5 % лише робіт
    order.manual_discount_pct = 10
    # 10 % замість 5 % на роботи + 10 % на запчастини, знижки не додаються
    assert order.discount_amount() == Money.from_uah("340")
    assert order.total() == Money.from_uah("3060")


def test_labor_hours_count_only_works(new_order, brake_job, brake_pads):
    new_order.add_work(brake_job, 2)
    new_order.add_part(brake_pads, 1)
    assert new_order.labor_hours() == 1.6


# ---- статуси ----------------------------------------------------------------

def test_cannot_start_without_works(new_order):
    with pytest.raises(BusinessRuleError):
        new_order.change_status(OrderStatus.IN_PROGRESS, NOW)
    assert new_order.status is OrderStatus.NEW


def test_skipping_status_is_not_allowed(new_order, brake_job):
    new_order.add_work(brake_job, 1)
    with pytest.raises(InvalidTransitionError):
        new_order.change_status(OrderStatus.PAID, NOW)


def test_full_path_sets_dates_and_mileage(new_order, brake_job):
    new_order.add_work(brake_job, 1)
    new_order.change_status(OrderStatus.IN_PROGRESS, NOW)
    new_order.change_status(OrderStatus.COMPLETED, NOW + timedelta(hours=2))
    assert new_order.completed_at == NOW + timedelta(hours=2)
    assert new_order.car.mileage_km == 151_000
    new_order.change_status(OrderStatus.PAID, NOW + timedelta(hours=3))
    assert new_order.paid_at == NOW + timedelta(hours=3)
    assert new_order.state.allowed_next() == frozenset()


def test_rework_clears_completion_date(new_order, brake_job):
    new_order.add_work(brake_job, 1)
    new_order.change_status(OrderStatus.IN_PROGRESS, NOW)
    new_order.change_status(OrderStatus.COMPLETED, NOW)
    new_order.change_status(OrderStatus.IN_PROGRESS, NOW)
    assert new_order.completed_at is None
    assert new_order.state.lines_editable


def test_cancel_returns_parts_but_keeps_lines(new_order, brake_job,
                                              brake_pads):
    new_order.add_work(brake_job, 1)
    new_order.add_part(brake_pads, 3)
    new_order.change_status(OrderStatus.CANCELLED, NOW)
    assert brake_pads.stock_qty == 5
    assert len(new_order.lines()) == 2


def test_completed_order_is_locked(new_order, brake_job, brake_pads):
    new_order.add_work(brake_job, 1)
    new_order.change_status(OrderStatus.IN_PROGRESS, NOW)
    new_order.change_status(OrderStatus.COMPLETED, NOW)
    with pytest.raises(BusinessRuleError, match="Виконано"):
        new_order.add_part(brake_pads, 1)
    assert brake_pads.stock_qty == 5


def test_overdue_only_for_open_orders(new_order, brake_job):
    later = new_order.due_date + timedelta(days=1)
    assert not new_order.is_overdue(new_order.due_date)
    assert new_order.is_overdue(later)
    new_order.change_status(OrderStatus.CANCELLED, NOW)
    assert not new_order.is_overdue(later)
