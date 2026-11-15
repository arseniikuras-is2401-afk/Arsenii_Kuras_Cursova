"""Замовлення-наряд на ремонт автомобіля."""

from datetime import date, datetime, timedelta

from config import MAX_DUE_DAYS, MAX_MANUAL_DISCOUNT_PCT
from models.car import Car
from models.catalog import Part, WorkType
from models.discounts import (BestOfDiscount, DiscountPolicy, LoyaltyDiscount,
                              ManualDiscount, NoDiscount)
from models.errors import (BusinessRuleError, InvalidTransitionError,
                           ValidationError)
from models.money import ZERO, Money
from models.order_lines import LineKind, OrderLine, PartLine, WorkLine
from models.order_state import OrderState, OrderStatus
from models.person import Employee
from models.validators import (check_int_range, clean_text, parse_date,
                               parse_datetime)


class Order:
    """Агрегат замовлення: керує своїми рядками й статусом.

    Рядки створюються й видаляються лише методами замовлення, тому залишки
    запчастин і правила статусу неможливо обійти ззовні.
    """

    def __init__(self, car: Car, mechanic: Employee, complaint: str,
                 due_date: date, accepted_at: datetime | None = None,
                 intake_mileage_km: int | None = None,
                 manual_discount_pct: int = 0, loyalty_discount_pct: int = 0,
                 status: OrderStatus = OrderStatus.NEW,
                 completed_at: datetime | None = None,
                 paid_at: datetime | None = None,
                 order_id: int | None = None):
        self.order_id = order_id
        self.car = car
        self.mechanic = mechanic
        self._accepted_at = parse_datetime(
            accepted_at or datetime.now().replace(second=0, microsecond=0))
        self.due_date = due_date
        self.complaint = complaint
        self._intake_mileage_km = check_int_range(
            car.mileage_km if intake_mileage_km is None else intake_mileage_km,
            0, 5_000_000, "intake_mileage_km", "Пробіг при прийманні")
        self.manual_discount_pct = manual_discount_pct
        self._loyalty_discount_pct = check_int_range(
            loyalty_discount_pct, 0, 100, "loyalty_discount_pct",
            "Знижка постійного клієнта")
        self._state: OrderState = status.state
        self._completed_at = parse_datetime(completed_at) if completed_at \
            else None
        self._paid_at = parse_datetime(paid_at) if paid_at else None
        self._lines: list[OrderLine] = []

    @classmethod
    def open_new(cls, car: Car, mechanic: Employee, complaint: str,
                 due_date: date, intake_mileage_km: int,
                 manual_discount_pct: int = 0, loyalty_discount_pct: int = 0,
                 accepted_at: datetime | None = None) -> "Order":
        """Нове замовлення з перевірками, які стосуються лише створення.

        Для замовлень, прочитаних з бази, ці перевірки не застосовуються:
        пробіг авто з часом зріс, а механіка могли деактивувати.
        """
        if not mechanic.is_active:
            raise BusinessRuleError(
                f"Механік {mechanic.full_name()} неактивний")
        intake = check_int_range(intake_mileage_km, 0, 5_000_000,
                                 "intake_mileage_km", "Пробіг при прийманні")
        if intake < car.mileage_km:
            raise ValidationError(
                f"Пробіг не може бути меншим за "
                f"{car.mileage_km:,} км (останній візит)".replace(",", " "),
                field="intake_mileage_km")
        return cls(car, mechanic, complaint, due_date, accepted_at=accepted_at,
                   intake_mileage_km=intake,
                   manual_discount_pct=manual_discount_pct,
                   loyalty_discount_pct=loyalty_discount_pct)

    # ---- шапка замовлення -------------------------------------------------

    @property
    def number(self) -> str:
        """Номер для людей: «АС-000041»."""
        return format_order_number(self.order_id)

    @property
    def accepted_at(self) -> datetime:
        return self._accepted_at

    @property
    def due_date(self) -> date:
        return self._due_date

    @due_date.setter
    def due_date(self, value):
        due = parse_date(value, "due_date", "Плановий термін")
        accepted = self._accepted_at.date()
        if due < accepted:
            raise ValidationError(
                "Плановий термін не може бути раніше дати приймання",
                field="due_date")
        if due > accepted + timedelta(days=MAX_DUE_DAYS):
            raise ValidationError(
                f"Плановий термін — не пізніше ніж через {MAX_DUE_DAYS} днів "
                f"від приймання", field="due_date")
        self._due_date = due

    @property
    def complaint(self) -> str:
        return self._complaint

    @complaint.setter
    def complaint(self, value: str):
        self._complaint = clean_text(value, "complaint",
                                     "Скарга / що зробити", min_len=3,
                                     max_len=500)

    @property
    def intake_mileage_km(self) -> int:
        return self._intake_mileage_km

    @property
    def manual_discount_pct(self) -> int:
        return self._manual_discount_pct

    @manual_discount_pct.setter
    def manual_discount_pct(self, value: int):
        self._manual_discount_pct = check_int_range(
            value, 0, MAX_MANUAL_DISCOUNT_PCT, "manual_discount_pct",
            "Знижка, %")

    @property
    def loyalty_discount_pct(self) -> int:
        return self._loyalty_discount_pct

    @property
    def completed_at(self) -> datetime | None:
        return self._completed_at

    @property
    def paid_at(self) -> datetime | None:
        return self._paid_at

    # ---- статус -----------------------------------------------------------

    @property
    def status(self) -> OrderStatus:
        return self._state.status

    @property
    def state(self) -> OrderState:
        return self._state

    def change_status(self, new_status: OrderStatus, moment: datetime):
        """Переводить замовлення в новий статус, якщо перехід дозволений."""
        if not self._state.can_switch_to(new_status):
            raise InvalidTransitionError(
                f"Перехід «{self._state.title}» → «{new_status.title}» "
                f"неможливий")
        new_state = new_status.state
        new_state.check_enter(self)
        new_state.on_enter(self, moment)
        self._state = new_state

    def is_overdue(self, today: date) -> bool:
        """Відкрите замовлення, плановий термін якого минув."""
        return self._state.is_open and today > self._due_date

    # Методи нижче викликають класи станів при вході в статус.

    def mark_completed(self, moment: datetime):
        self._completed_at = moment
        self.car.register_mileage(self._intake_mileage_km)

    def clear_completion(self):
        self._completed_at = None

    def mark_paid(self, moment: datetime):
        self._paid_at = moment

    def release_all_parts(self):
        for line in self.part_lines():
            line.release_stock()

    # ---- рядки ------------------------------------------------------------

    def lines(self) -> tuple[OrderLine, ...]:
        return tuple(self._lines)

    def work_lines(self) -> tuple[WorkLine, ...]:
        return tuple(line for line in self._lines
                     if isinstance(line, WorkLine))

    def part_lines(self) -> tuple[PartLine, ...]:
        return tuple(line for line in self._lines
                     if isinstance(line, PartLine))

    def restore_line(self, line: OrderLine):
        """Додає рядок, прочитаний з бази, без зміни складу й перевірок."""
        self._lines.append(line)

    def add_work(self, work_type: WorkType, quantity: int) -> WorkLine:
        self._ensure_editable()
        if not work_type.is_active:
            raise BusinessRuleError(
                f"Роботу «{work_type.name}» виведено з прайсу")
        line = WorkLine(work_type, quantity)
        self._lines.append(line)
        return line

    def add_part(self, part: Part, quantity: int) -> PartLine:
        """Списує запчастину зі складу; повторна запчастина збільшує рядок."""
        self._ensure_editable()
        existing = self.find_part_line(part)
        if existing is not None:
            # Перевіряємо межу кількості до списання, щоб не змінити склад
            # і не отримати потім помилку валідації рядка.
            check_int_range(existing.quantity + quantity, 1,
                            PartLine.MAX_QUANTITY, "quantity", "Кількість")
        if existing is not None:
            # Списуємо з того самого об'єкта, що вже належить рядку, щоб
            # у пам'яті не було двох різних залишків однієї запчастини.
            existing.part.take(quantity)
            existing.quantity += quantity
            return existing
        part.take(quantity)
        line = PartLine(part, quantity)
        self._lines.append(line)
        return line

    def remove_line(self, line: OrderLine):
        self._ensure_editable()
        if line not in self._lines:
            raise BusinessRuleError("Цього рядка немає в замовленні")
        if isinstance(line, PartLine):
            line.release_stock()
        self._lines.remove(line)

    def find_part_line(self, part: Part) -> PartLine | None:
        """Рядок цієї запчастини (той самий об'єкт або той самий id у базі)."""
        for line in self.part_lines():
            same_record = (part.part_id is not None
                           and line.part.part_id == part.part_id)
            if line.part is part or same_record:
                return line
        return None

    def find_line(self, kind: LineKind, line_id: int) -> OrderLine:
        for line in self._lines:
            if line.kind() is kind and line.line_id == line_id:
                return line
        raise BusinessRuleError(
            "Рядок не знайдено; можливо, його вже видалено")

    def _ensure_editable(self):
        if not self._state.lines_editable:
            raise BusinessRuleError(self._state.locked_reason())

    # ---- суми -------------------------------------------------------------

    def discount_policy(self) -> DiscountPolicy:
        policies = []
        if self._manual_discount_pct:
            policies.append(ManualDiscount(self._manual_discount_pct))
        if self._loyalty_discount_pct:
            policies.append(LoyaltyDiscount(self._loyalty_discount_pct))
        return BestOfDiscount(policies) if policies else NoDiscount()

    def sum_of(self, kind: LineKind) -> Money:
        total = ZERO
        for line in self._lines:
            if line.kind() is kind:
                total += line.total()
        return total

    def subtotal(self) -> Money:
        return self.sum_of(LineKind.WORK) + self.sum_of(LineKind.PART)

    def discount_amount(self) -> Money:
        """Знижка рахується від суми кожного виду рядків, як у v_order_list."""
        policy = self.discount_policy()
        discount = ZERO
        for kind in LineKind:
            discount += self.sum_of(kind).percent(policy.percent_for(kind))
        return discount

    def total(self) -> Money:
        return self.subtotal() - self.discount_amount()

    def labor_hours(self) -> float:
        return round(sum(line.labor_hours() for line in self._lines), 2)


def format_order_number(order_id: int | None) -> str:
    return f"АС-{order_id:06d}" if order_id else "АС-(нове)"
