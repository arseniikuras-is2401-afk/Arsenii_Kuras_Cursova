"""Заповнення нової бази демонстраційними даними.

Замовлення проходять через ті самі методи моделей, що й у програмі
(списання запчастин, переходи статусів, знижки), тому демо-дані
відповідають усім правилам предметної області.
"""

import random
from datetime import date, datetime, time, timedelta

from config import (DEMO_SEED, LOYALTY_DISCOUNT_PCT, LOYALTY_MIN_PAID_ORDERS,
                    MAX_OPEN_ORDERS_PER_MECHANIC)
from database import demo_data as data
from database.unit_of_work import UnitOfWork
from models import (Car, Client, Employee, Money, Order, OrderStatus, Part,
                    RepairCategory, WorkType)

DEMO_DAYS = 180
ORDERS_COUNT = 150
EXTRA_CARS = 10
INACTIVE_MECHANIC_UNTIL_DAYS_AGO = 40


class DemoSeeder:
    """Генерує однаковий на будь-якому комп'ютері набір даних."""

    def __init__(self, now: datetime | None = None, seed: int = DEMO_SEED):
        self._rng = random.Random(seed)
        self._now = (now or datetime.now()).replace(second=0, microsecond=0)
        self._today = self._now.date()
        self._categories: dict[str, RepairCategory] = {}
        self._work_types: dict[str, WorkType] = {}
        self._parts: dict[str, Part] = {}
        self._employees: list[Employee] = []
        self._clients: list[Client] = []
        self._cars: list[Car] = []
        self._used_phones: set[str] = set()
        self._used_plates: set[str] = set()
        # Механіки, яких деактивують після генерації замовлень: до того
        # вони встигають виконати кілька старих замовлень.
        self._retiring: set[int] = set()

    def seed(self, uow: UnitOfWork):
        """Записує всі дані в межах переданої транзакції."""
        self._seed_catalog(uow)
        self._seed_employees(uow)
        self._seed_clients_and_cars(uow)
        self._seed_orders(uow)
        self._finish_stock(uow)
        self._retire_employees(uow)

    # ---- довідники ----------------------------------------------------------

    def _seed_catalog(self, uow: UnitOfWork):
        for name in data.CATEGORIES:
            category = RepairCategory(name)
            uow.categories.insert(category)
            self._categories[name] = category
        for category, name, price, hours, active in data.WORK_TYPES:
            work_type = WorkType(self._categories[category], name,
                                 Money.from_uah(price), hours, active)
            uow.work_types.insert(work_type)
            self._work_types[name] = work_type
        for category, article, name, price, min_qty in data.PARTS:
            part = Part(self._categories[category], article, name,
                        Money.from_uah(price),
                        stock_qty=self._rng.randint(min_qty * 3,
                                                    min_qty * 6 + 10),
                        min_qty=min_qty)
            uow.parts.insert(part)
            self._parts[article] = part

    def _seed_employees(self, uow: UnitOfWork):
        for last, first, category, year, active in data.EMPLOYEES:
            employee = Employee(
                last, first, self._new_phone(),
                hired_on=date(year, self._rng.randint(1, 12),
                              self._rng.randint(1, 28)),
                specialization=self._categories[category])
            uow.employees.insert(employee)
            if not active:
                self._retiring.add(employee.employee_id)
            self._employees.append(employee)

    def _seed_clients_and_cars(self, uow: UnitOfWork):
        period_start = self._today - timedelta(days=DEMO_DAYS)
        for index, (last, first) in enumerate(data.CLIENT_NAMES):
            if index < 22:
                registered = period_start - timedelta(
                    days=self._rng.randint(0, 900))
            else:
                registered = period_start + timedelta(
                    days=self._rng.randint(0, DEMO_DAYS - 20))
            email = None
            if self._rng.random() < 0.6:
                email = (f"{data.transliterate(last)}"
                         f"{self._rng.randint(1, 99)}@"
                         f"{self._rng.choice(data.EMAIL_DOMAINS)}")
            note = (self._rng.choice(data.CLIENT_NOTES)
                    if self._rng.random() < 0.15 else None)
            client = Client(last, first, self._new_phone(), email=email,
                            registered_on=registered, note=note)
            uow.clients.insert(client)
            self._clients.append(client)
        owners = self._clients + self._rng.sample(self._clients, EXTRA_CARS)
        for owner in owners:
            make, model, first_year, last_year = self._rng.choice(
                data.CAR_MODELS)
            year = self._rng.randint(first_year, last_year)
            age = max(self._today.year - year, 1)
            vin = (None if self._rng.random() < 0.25 else "".join(
                self._rng.choice(data.VIN_ALPHABET) for _ in range(17)))
            car = Car(owner, make, model, year, self._new_plate(), vin=vin,
                      mileage_km=age * self._rng.randint(9_000, 18_000))
            uow.cars.insert(car)
            self._cars.append(car)

    # ---- замовлення ---------------------------------------------------

    def _seed_orders(self, uow: UnitOfWork):
        open_by_car: set[int] = set()
        open_by_mechanic: dict[int, int] = {}
        paid_by_client: dict[int, int] = {}
        for accepted in self._order_moments():
            days_ago = (self._today - accepted.date()).days
            car = self._pick_car(accepted, open_by_car)
            mechanic = self._pick_mechanic(days_ago, open_by_mechanic)
            if car is None or mechanic is None:
                continue
            client_id = car.owner.client_id
            loyal = paid_by_client.get(client_id, 0) >= LOYALTY_MIN_PAID_ORDERS
            complaint, works = self._rng.choice(data.SCENARIOS)
            order = Order.open_new(
                car, mechanic, complaint,
                accepted.date() + timedelta(days=self._rng.randint(1, 7)),
                intake_mileage_km=car.mileage_km + self._rng.randint(
                    500, 9_000),
                manual_discount_pct=self._rng.choice((0,) * 8 + (5, 10)),
                loyalty_discount_pct=LOYALTY_DISCOUNT_PCT if loyal else 0,
                accepted_at=accepted)
            uow.orders.insert(order)
            uow.orders.log_status(order.order_id, None, OrderStatus.NEW,
                                  accepted)
            self._fill_lines(uow, order, works)
            final = self._final_status(days_ago)
            if final in (OrderStatus.NEW, OrderStatus.IN_PROGRESS):
                load = open_by_mechanic.get(mechanic.employee_id, 0)
                if load >= MAX_OPEN_ORDERS_PER_MECHANIC:
                    final = OrderStatus.COMPLETED
            self._advance(uow, order, final)
            if order.state.is_open:
                open_by_car.add(car.car_id)
                open_by_mechanic[mechanic.employee_id] = \
                    open_by_mechanic.get(mechanic.employee_id, 0) + 1
            if order.status is OrderStatus.PAID:
                paid_by_client[client_id] = paid_by_client.get(client_id,
                                                               0) + 1

    def _order_moments(self) -> list[datetime]:
        """Моменти приймання авто: робочі години, рівномірно за період."""
        moments = []
        for number in range(ORDERS_COUNT):
            # П'ята частина замовлень — за останні 10 днів, щоб у демо були
            # відкриті й прострочені замовлення.
            span = 10 if number < ORDERS_COUNT // 5 else DEMO_DAYS
            day = self._today - timedelta(days=self._rng.randint(0, span))
            if day.weekday() == 6:  # неділя — вихідний
                day -= timedelta(days=1)
            moment = datetime.combine(day, time(self._rng.randint(8, 17),
                                                self._rng.choice((0, 15, 30,
                                                                  45))))
            moments.append(min(moment, self._now - timedelta(minutes=30)))
        return sorted(moments)

    def _pick_car(self, accepted: datetime, open_by_car: set[int]):
        candidates = [car for car in self._cars
                      if car.car_id not in open_by_car
                      and car.owner.registered_on <= accepted.date()]
        return self._rng.choice(candidates) if candidates else None

    def _pick_mechanic(self, days_ago: int, open_by_mechanic: dict[int, int]):
        candidates = [
            employee for employee in self._employees
            if (employee.employee_id not in self._retiring
                or days_ago > INACTIVE_MECHANIC_UNTIL_DAYS_AGO)]
        if days_ago <= 10:
            candidates = [employee for employee in candidates
                          if open_by_mechanic.get(employee.employee_id, 0)
                          < MAX_OPEN_ORDERS_PER_MECHANIC]
        return self._rng.choice(candidates) if candidates else None

    def _fill_lines(self, uow: UnitOfWork, order: Order, works):
        for work_name, quantity in works:
            line = order.add_work(self._work_types[work_name], quantity)
            uow.orders.save_line(order, line)
            for articles, per_work in data.WORK_PARTS.get(work_name, ()):
                part = self._parts[self._rng.choice(articles)]
                needed = per_work * quantity
                if part.stock_qty < needed:
                    part.receive(needed + part.min_qty * 3)  # постачання
                part_line = order.add_part(part, needed)
                uow.orders.save_line(order, part_line)
                uow.parts.update_stock(part)

    def _final_status(self, days_ago: int) -> OrderStatus:
        roll = self._rng.random()
        if days_ago > 10:
            if roll < 0.08:
                return OrderStatus.CANCELLED
            if roll < 0.11 and days_ago < 25:
                return OrderStatus.COMPLETED
            return OrderStatus.PAID
        if days_ago > 3:
            for limit, status in ((0.55, OrderStatus.PAID),
                                  (0.75, OrderStatus.COMPLETED),
                                  (0.88, OrderStatus.IN_PROGRESS)):
                if roll < limit:
                    return status
            return OrderStatus.CANCELLED
        for limit, status in ((0.35, OrderStatus.NEW),
                              (0.80, OrderStatus.IN_PROGRESS),
                              (0.95, OrderStatus.COMPLETED)):
            if roll < limit:
                return status
        return OrderStatus.PAID

    def _advance(self, uow: UnitOfWork, order: Order, final: OrderStatus):
        """Проводить замовлення статусами до `final` з правдоподібним часом."""
        if final is OrderStatus.NEW:
            return
        moment = order.accepted_at
        path = {
            OrderStatus.IN_PROGRESS: (OrderStatus.IN_PROGRESS,),
            OrderStatus.COMPLETED: (OrderStatus.IN_PROGRESS,
                                    OrderStatus.COMPLETED),
            OrderStatus.PAID: (OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED,
                               OrderStatus.PAID),
            OrderStatus.CANCELLED: ((OrderStatus.IN_PROGRESS,
                                     OrderStatus.CANCELLED)
                                    if self._rng.random() < 0.5
                                    else (OrderStatus.CANCELLED,)),
        }[final]
        for status in path:
            moment = self._next_moment(moment, status, order)
            old = order.status
            order.change_status(status, moment)
            comment = ("Клієнт відмовився від ремонту"
                       if status is OrderStatus.CANCELLED else None)
            uow.orders.log_status(order.order_id, old, status, moment,
                                  comment)
        uow.orders.update_status(order)
        if order.status in (OrderStatus.COMPLETED, OrderStatus.PAID):
            uow.cars.update_mileage(order.car)
        if order.status is OrderStatus.CANCELLED:
            for line in order.part_lines():
                uow.parts.update_stock(line.part)

    def _next_moment(self, previous: datetime, status: OrderStatus,
                     order: Order) -> datetime:
        if status is OrderStatus.IN_PROGRESS:
            delay = timedelta(minutes=self._rng.randint(20, 180))
        elif status is OrderStatus.COMPLETED:
            delay = timedelta(hours=order.labor_hours() * 1.5
                              + self._rng.randint(1, 30))
        elif status is OrderStatus.PAID:
            delay = timedelta(hours=self._rng.randint(1, 48))
        else:
            delay = timedelta(hours=self._rng.randint(1, 24))
        latest = self._now - timedelta(minutes=5)
        candidate = previous + delay
        if candidate > latest:
            # Для свіжих замовлень події стискаються до поточного моменту.
            candidate = max(previous + timedelta(minutes=1),
                            previous + (latest - previous) / 2)
        return candidate.replace(second=0, microsecond=0)

    # ---- склад ------------------------------------------------------------

    def _finish_stock(self, uow: UnitOfWork):
        """Кілька запчастин опускаються нижче мінімуму — для демонстрації."""
        scarcest = sorted(self._parts.values(),
                          key=lambda item: (item.stock_qty, item.article))
        for part in scarcest[:6]:
            part.min_qty = part.stock_qty + self._rng.randint(1, 4)
            uow.parts.update(part)

    def _retire_employees(self, uow: UnitOfWork):
        for employee in self._employees:
            if employee.employee_id in self._retiring:
                employee.is_active = False
                uow.employees.update(employee)

    # ---- унікальні значення -------------------------------------------------

    def _new_phone(self) -> str:
        while True:
            phone = (self._rng.choice(data.PHONE_CODES)
                     + f"{self._rng.randint(0, 9_999_999):07d}")
            if phone not in self._used_phones:
                self._used_phones.add(phone)
                return phone

    def _new_plate(self) -> str:
        while True:
            plate = (self._rng.choice(data.PLATE_REGIONS)
                     + f"{self._rng.randint(0, 9999):04d}"
                     + "".join(self._rng.choice(data.PLATE_LETTERS)
                               for _ in range(2)))
            if plate not in self._used_plates:
                self._used_plates.add(plate)
                return plate
