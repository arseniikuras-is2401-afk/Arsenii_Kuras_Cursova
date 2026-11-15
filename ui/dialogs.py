"""Конкретні форми застосунку, побудовані з декларативних полів."""

from datetime import date, timedelta

from PyQt5.QtWidgets import QLabel

from config import (LOYALTY_DISCOUNT_PCT, MAX_MANUAL_DISCOUNT_PCT,
                    MAX_WORK_QUANTITY, MIN_PRODUCTION_YEAR)
from models import (Car, Client, Employee, Part, RepairCategory,
                    ValidationError, WorkType)
from models.order import Order
from services import AppContext
from ui import formatting
from ui.forms import (CheckField, ChoiceField, DateField, DecimalField,
                      FieldSpec, FormDialog, IntField, MoneyField,
                      MultilineField, PhoneField, TextField)


def _info_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "info")
    label.setWordWrap(True)
    label.setVisible(bool(text))
    return label


# ---- клієнти й авто ---------------------------------------------------------


class ClientForm(FormDialog):
    def __init__(self, app: AppContext, client: Client | None = None,
                 parent=None):
        self._app, self._client = app, client
        self.saved_id: int | None = None
        super().__init__("Редагування клієнта" if client else "Новий клієнт",
                         parent)
        if client:
            self.set_values({"last_name": client.last_name,
                             "first_name": client.first_name,
                             "phone": client.phone, "email": client.email,
                             "note": client.note})

    def fields(self) -> list[FieldSpec]:
        return [
            TextField("last_name", "Прізвище", True, max_length=50,
                      placeholder="Іваненко"),
            TextField("first_name", "Ім'я", True, max_length=50,
                      placeholder="Петро"),
            PhoneField(),
            TextField("email", "Email", placeholder="petro@ukr.net",
                      max_length=100),
            MultilineField("note", "Примітка",
                           placeholder="Наприклад: телефонувати після 18:00"),
        ]

    def submit(self, values: dict):
        old = self._client
        client = Client(values["last_name"], values["first_name"],
                        values["phone"], email=values["email"],
                        registered_on=old.registered_on if old else None,
                        note=values["note"],
                        client_id=old.client_id if old else None)
        self.saved_id = self._app.customers.save_client(client)


class CarForm(FormDialog):
    def __init__(self, app: AppContext, car: Car | None = None,
                 owner_id: int | None = None, parent=None):
        self._app, self._car = app, car
        self.saved_id: int | None = None
        super().__init__("Редагування авто" if car else "Новий автомобіль",
                         parent)
        if car:
            self.set_values({"owner": car.owner.client_id, "make": car.make,
                             "model": car.model,
                             "production_year": car.production_year,
                             "plate_number": car.plate_number,
                             "vin": car.vin, "mileage_km": car.mileage_km})
        else:
            self.set_values({"owner": owner_id, "production_year": 2015})

    def fields(self) -> list[FieldSpec]:
        clients = [(client.display_name(), client.client_id)
                   for client in self._app.customers.all_clients()]
        year = date.today().year
        return [
            ChoiceField("owner", "Власник", lambda: clients),
            TextField("make", "Марка", True, placeholder="Toyota",
                      max_length=40),
            TextField("model", "Модель", True, placeholder="Corolla",
                      max_length=40),
            IntField("production_year", "Рік випуску", MIN_PRODUCTION_YEAR,
                     year + 1),
            TextField("plate_number", "Держномер", True,
                      placeholder="AT1234BC", max_length=12,
                      hint="Кириличні літери буде замінено латинськими"),
            TextField("vin", "VIN", placeholder="17 символів, необов'язково",
                      max_length=17),
            IntField("mileage_km", "Пробіг", 0, 5_000_000, "км", step=1000),
        ]

    def submit(self, values: dict):
        owner = self._app.customers.get_client(values["owner"])
        car = Car(owner, values["make"], values["model"],
                  values["production_year"], values["plate_number"],
                  vin=values["vin"], mileage_km=values["mileage_km"],
                  car_id=self._car.car_id if self._car else None)
        self.saved_id = self._app.customers.save_car(car)


# ---- механіки й довідники ---------------------------------------------------


class EmployeeForm(FormDialog):
    def __init__(self, app: AppContext, employee: Employee | None = None,
                 parent=None):
        self._app, self._employee = app, employee
        self.saved_id: int | None = None
        super().__init__("Редагування механіка" if employee
                         else "Новий механік", parent)
        if employee:
            spec = employee.specialization
            self.set_values({"last_name": employee.last_name,
                             "first_name": employee.first_name,
                             "phone": employee.phone,
                             "category": spec.category_id if spec else None,
                             "hired_on": employee.hired_on,
                             "is_active": employee.is_active})
        else:
            self.set_values({"is_active": True})

    def fields(self) -> list[FieldSpec]:
        categories = [(category.name, category.category_id)
                      for category in self._app.catalog.categories()]
        return [
            TextField("last_name", "Прізвище", True, max_length=50),
            TextField("first_name", "Ім'я", True, max_length=50),
            PhoneField(),
            ChoiceField("category", "Спеціалізація", lambda: categories,
                        required=False, empty_text="Без спеціалізації"),
            DateField("hired_on", "Дата прийому"),
            CheckField("is_active", "Працює (можна доручати замовлення)"),
        ]

    def submit(self, values: dict):
        category = None
        if values["category"]:
            category = next(item for item in self._app.catalog.categories()
                            if item.category_id == values["category"])
        employee = Employee(
            values["last_name"], values["first_name"], values["phone"],
            hired_on=values["hired_on"], specialization=category,
            is_active=values["is_active"],
            employee_id=self._employee.employee_id if self._employee
            else None)
        self.saved_id = self._app.staff.save(employee)


class CategoryForm(FormDialog):
    def __init__(self, app: AppContext,
                 category: RepairCategory | None = None, parent=None):
        self._app, self._category = app, category
        super().__init__("Редагування категорії" if category
                         else "Нова категорія", parent)
        if category:
            self.set_values({"name": category.name})

    def fields(self) -> list[FieldSpec]:
        return [TextField("name", "Назва", True, max_length=60,
                          placeholder="Наприклад: Кондиціонер")]

    def submit(self, values: dict):
        category = RepairCategory(
            values["name"],
            self._category.category_id if self._category else None)
        self._app.catalog.save_category(category)


def _category_choices(app: AppContext):
    return [(category.name, category.category_id)
            for category in app.catalog.categories()]


def _category(app: AppContext, category_id: int) -> RepairCategory:
    return next(item for item in app.catalog.categories()
                if item.category_id == category_id)


class WorkTypeForm(FormDialog):
    def __init__(self, app: AppContext, work_type: WorkType | None = None,
                 parent=None):
        self._app, self._work_type = app, work_type
        super().__init__("Редагування роботи" if work_type
                         else "Нова робота в прайсі", parent)
        if work_type:
            self.set_values({"category": work_type.category.category_id,
                             "name": work_type.name,
                             "price": work_type.price,
                             "norm_hours": work_type.norm_hours,
                             "is_active": work_type.is_active})
        else:
            self.set_values({"norm_hours": 1.0, "is_active": True})

    def fields(self) -> list[FieldSpec]:
        choices = _category_choices(self._app)
        return [
            ChoiceField("category", "Категорія", lambda: choices),
            TextField("name", "Назва", True, max_length=120,
                      placeholder="Заміна гальмівних колодок"),
            MoneyField("price", "Ціна, грн"),
            DecimalField("norm_hours", "Нормо-години", 0.1, 100, 2, 0.1,
                         "год", hint="Скільки часу робота займає за "
                                     "нормативом; потрібно для "
                                     "завантаженості механіків"),
            CheckField("is_active", "Активна (можна додавати в замовлення)"),
        ]

    def submit(self, values: dict):
        work_type = WorkType(
            _category(self._app, values["category"]), values["name"],
            values["price"], values["norm_hours"],
            is_active=values["is_active"],
            work_type_id=self._work_type.work_type_id if self._work_type
            else None)
        self._app.catalog.save_work_type(work_type)


class PartForm(FormDialog):
    def __init__(self, app: AppContext, part: Part | None = None,
                 parent=None):
        self._app, self._part = app, part
        self.saved_id: int | None = None
        super().__init__("Редагування запчастини" if part
                         else "Нова запчастина", parent)
        if part:
            self.set_values({"category": part.category.category_id,
                             "article": part.article, "name": part.name,
                             "price": part.price, "min_qty": part.min_qty})
            self.extra.addWidget(_info_label(
                f"Залишок на складі: {part.stock_qty} шт. Він змінюється "
                f"лише приходом і замовленнями."))

    def fields(self) -> list[FieldSpec]:
        choices = _category_choices(self._app)
        specs = [
            ChoiceField("category", "Категорія", lambda: choices),
            TextField("article", "Артикул", True, max_length=30,
                      placeholder="BRK-PAD-F01"),
            TextField("name", "Назва", True, max_length=120),
            MoneyField("price", "Ціна продажу, грн"),
            IntField("min_qty", "Мінімальний залишок", 0, 10_000, "шт.",
                     hint="Нижче цього рівня запчастина підсвічується"),
        ]
        if self._part is None:
            specs.append(IntField("stock_qty", "Початковий залишок", 0,
                                  10_000, "шт."))
        return specs

    def submit(self, values: dict):
        part = self._part
        result = Part(_category(self._app, values["category"]),
                      values["article"], values["name"], values["price"],
                      stock_qty=part.stock_qty if part
                      else values["stock_qty"],
                      min_qty=values["min_qty"],
                      part_id=part.part_id if part else None)
        self.saved_id = self._app.catalog.save_part(result)


class ReceivePartsDialog(FormDialog):
    SUBMIT_TEXT = "Оприбуткувати"

    def __init__(self, app: AppContext, part: Part, parent=None):
        self._app, self._part = app, part
        super().__init__(
            "Прихід запчастин", parent,
            intro=f"{part.name} [{part.article}]. Зараз на складі: "
                  f"{part.stock_qty} шт.")
        self.set_values({"quantity": max(part.min_qty, 1)})

    def fields(self) -> list[FieldSpec]:
        return [IntField("quantity", "Кількість", 1, 10_000, "шт.")]

    def submit(self, values: dict):
        self._app.catalog.receive_parts(self._part.part_id,
                                        values["quantity"])


# ---- замовлення -------------------------------------------------------------


def _mechanic_choices(app: AppContext, keep_id: int | None = None):
    return [(f"{employee.display_name()} · відкритих: {load}",
             employee.employee_id)
            for employee, load in app.staff.available_mechanics(keep_id)]


class NewOrderForm(FormDialog):
    """Оформлення замовлення: клієнт → його авто → механік → деталі."""

    SUBMIT_TEXT = "Оформити"

    def __init__(self, app: AppContext, car_id: int | None = None,
                 parent=None):
        self._app = app
        self.order_id: int | None = None
        self._cars: dict[int, Car] = {}
        super().__init__("Нове замовлення", parent)
        self.setMinimumWidth(600)
        self._info = _info_label()
        self.extra.addWidget(self._info)
        self.widget("client").currentIndexChanged.connect(
            self._on_client_changed)
        self.widget("car").currentIndexChanged.connect(self._on_car_changed)
        self.set_values({"due_date": date.today() + timedelta(days=2)})
        if car_id:
            car = app.customers.get_car(car_id)
            self.set_values({"client": car.owner.client_id})
            self._on_client_changed()
            self.set_values({"car": car_id})
        self._on_client_changed()

    def fields(self) -> list[FieldSpec]:
        clients = [(client.display_name(), client.client_id)
                   for client in self._app.customers.all_clients()]
        mechanics = _mechanic_choices(self._app)
        return [
            ChoiceField("client", "Клієнт", lambda: clients,
                        hint="Почніть вводити прізвище або телефон"),
            ChoiceField("car", "Автомобіль", lambda: []),
            ChoiceField("mechanic", "Механік", lambda: mechanics,
                        hint="Лише активні механіки з менш ніж 4 "
                             "відкритими замовленнями"),
            IntField("intake_mileage_km", "Пробіг при прийманні", 0,
                     5_000_000, "км", step=100),
            DateField("due_date", "Плановий термін", minimum=date.today()),
            MultilineField("complaint", "Скарга / що зробити", True,
                           placeholder="Наприклад: стук у передній "
                                       "підвісці"),
            IntField("manual_discount_pct", "Знижка майстра", 0,
                     MAX_MANUAL_DISCOUNT_PCT, "%"),
        ]

    def _on_client_changed(self, *_):
        client_id = self.spec("client").read(self.widget("client"))
        cars = self._app.customers.cars_of(client_id) if client_id else []
        self._cars = {car.car_id: car for car in cars}
        self.spec("car").fill(self.widget("car"),
                              [(car.display_name(), car.car_id)
                               for car in cars])
        self._on_car_changed()

    def _on_car_changed(self, *_):
        car = self._cars.get(self.spec("car").read(self.widget("car")))
        notes = []
        if car:
            self.widget("intake_mileage_km").setValue(car.mileage_km)
            self.widget("intake_mileage_km").setToolTip(
                f"Останній відомий пробіг: "
                f"{formatting.integer(car.mileage_km)} км")
            if self._app.orders.loyalty_percent(car.owner.client_id):
                notes.append(f"Постійний клієнт: знижка "
                             f"{LOYALTY_DISCOUNT_PCT} % на роботи "
                             f"нарахується автоматично.")
        client_id = self.spec("client").read(self.widget("client"))
        if client_id and not self._cars:
            notes.append("У клієнта ще немає автомобілів. Додайте авто на "
                         "сторінці «Клієнти».")
        self._info.setText(" ".join(notes))
        self._info.setVisible(bool(notes))
        self._update_submit()

    def submit(self, values: dict):
        if values["car"] is None:
            raise ValidationError("Оберіть автомобіль", field="car")
        self.order_id = self._app.orders.create(
            values["car"], values["mechanic"], values["complaint"],
            values["due_date"], values["intake_mileage_km"],
            values["manual_discount_pct"])


class OrderHeaderForm(FormDialog):
    def __init__(self, app: AppContext, order: Order, parent=None):
        self._app, self._order = app, order
        super().__init__(f"Замовлення {order.number}", parent,
                         intro=f"{order.car.title()}, "
                               f"{order.car.owner.full_name()}")
        self.set_values({"mechanic": order.mechanic.employee_id,
                         "due_date": order.due_date,
                         "complaint": order.complaint,
                         "manual_discount_pct": order.manual_discount_pct})

    def fields(self) -> list[FieldSpec]:
        mechanics = _mechanic_choices(self._app,
                                      self._order.mechanic.employee_id)
        return [
            ChoiceField("mechanic", "Механік", lambda: mechanics),
            DateField("due_date", "Плановий термін",
                      minimum=self._order.accepted_at.date()),
            MultilineField("complaint", "Скарга / що зробити", True),
            IntField("manual_discount_pct", "Знижка майстра", 0,
                     MAX_MANUAL_DISCOUNT_PCT, "%"),
        ]

    def submit(self, values: dict):
        self._app.orders.update_header(
            self._order.order_id, values["mechanic"], values["due_date"],
            values["complaint"], values["manual_discount_pct"])


class AddWorkDialog(FormDialog):
    SUBMIT_TEXT = "Додати"

    def __init__(self, app: AppContext, order_id: int, parent=None):
        self._app, self._order_id = app, order_id
        self._prices = {}
        super().__init__("Додати роботу", parent)
        self._preview = _info_label()
        self.extra.addWidget(self._preview)
        for name in ("work", "quantity"):
            self.spec(name).change_signal(self.widget(name)).connect(
                self._update_preview)
        self.set_values({"quantity": 1})
        self._update_preview()

    def fields(self) -> list[FieldSpec]:
        works = self._app.catalog.active_work_types()
        self._prices = {work.work_type_id: work.price for work in works}
        options = [(f"{work.name} — {work.price} · "
                    f"{formatting.number(work.norm_hours, 2)} н-год",
                    work.work_type_id) for work in works]
        return [ChoiceField("work", "Робота", lambda: options,
                            hint="Пошук за назвою"),
                IntField("quantity", "Кількість", 1, MAX_WORK_QUANTITY)]

    def _update_preview(self, *_):
        work_id = self.spec("work").read(self.widget("work"))
        if work_id in self._prices:
            total = self._prices[work_id] * self.widget("quantity").value()
            self._preview.setText(f"Сума рядка: {total}")
            self._preview.show()

    def submit(self, values: dict):
        self._app.orders.add_work(self._order_id, values["work"],
                                  values["quantity"])


class AddPartDialog(FormDialog):
    SUBMIT_TEXT = "Додати"

    def __init__(self, app: AppContext, order_id: int, parent=None):
        self._app, self._order_id = app, order_id
        self._parts: dict[int, Part] = {}
        super().__init__("Додати запчастину", parent,
                         intro="Запчастина одразу списується зі складу.")
        self._preview = _info_label()
        self.extra.addWidget(self._preview)
        self.widget("part").currentIndexChanged.connect(self._on_part)
        self.widget("quantity").valueChanged.connect(self._on_part)
        self._on_part()

    def fields(self) -> list[FieldSpec]:
        parts = self._app.catalog.parts_in_stock()
        self._parts = {part.part_id: part for part in parts}
        options = [(f"{part.name} [{part.article}] · {part.stock_qty} шт. "
                    f"· {part.price}", part.part_id) for part in parts]
        return [ChoiceField("part", "Запчастина", lambda: options,
                            hint="Пошук за назвою або артикулом; у списку "
                                 "лише те, що є на складі"),
                IntField("quantity", "Кількість", 1, 10_000, "шт.")]

    def _on_part(self, *_):
        part = self._parts.get(self.spec("part").read(self.widget("part")))
        spin = self.widget("quantity")
        if part is None:
            self._preview.hide()
            return
        spin.setMaximum(part.stock_qty)
        spin.setToolTip(f"На складі {part.stock_qty} шт.")
        self._preview.setText(
            f"Сума рядка: {part.price * spin.value()}. Після списання на "
            f"складі лишиться {part.stock_qty - spin.value()} шт.")
        self._preview.show()

    def submit(self, values: dict):
        self._app.orders.add_part(self._order_id, values["part"],
                                  values["quantity"])


class CommentDialog(FormDialog):
    """Підтвердження дії з необов'язковим коментарем для історії."""

    def __init__(self, title: str, intro: str, submit_text: str,
                 required: bool = False, danger: bool = False,
                 parent=None):
        self.SUBMIT_TEXT = submit_text
        self.SUBMIT_VARIANT = "danger" if danger else "primary"
        self._required = required
        self.comment: str | None = None
        super().__init__(title, parent, intro=intro)

    def fields(self) -> list[FieldSpec]:
        return [MultilineField("comment", "Коментар", self._required,
                               placeholder="Буде збережено в історії "
                                           "статусів", max_length=300)]

    def submit(self, values: dict):
        self.comment = values["comment"] or None
