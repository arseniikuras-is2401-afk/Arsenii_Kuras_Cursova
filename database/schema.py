"""Створення таблиць, індексів і представлень бази даних."""

import sqlite3

from config import LOYALTY_MIN_PAID_ORDERS

_TABLES = """
CREATE TABLE clients (
    client_id     INTEGER PRIMARY KEY,
    last_name     TEXT NOT NULL CHECK (length(last_name) BETWEEN 2 AND 50),
    first_name    TEXT NOT NULL CHECK (length(first_name) BETWEEN 2 AND 50),
    phone         TEXT NOT NULL UNIQUE CHECK (length(phone) = 10),
    email         TEXT UNIQUE,
    registered_on TEXT NOT NULL CHECK (date(registered_on) IS NOT NULL),
    note          TEXT
);

CREATE TABLE cars (
    car_id          INTEGER PRIMARY KEY,
    client_id       INTEGER NOT NULL
                    REFERENCES clients (client_id) ON DELETE RESTRICT,
    make            TEXT NOT NULL,
    model           TEXT NOT NULL,
    production_year INTEGER NOT NULL
                    CHECK (production_year BETWEEN 1950 AND 2100),
    plate_number    TEXT NOT NULL UNIQUE CHECK (length(plate_number) = 8),
    vin             TEXT UNIQUE CHECK (vin IS NULL OR length(vin) = 17),
    mileage_km      INTEGER NOT NULL DEFAULT 0 CHECK (mileage_km >= 0)
);

CREATE TABLE repair_categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    last_name   TEXT NOT NULL,
    first_name  TEXT NOT NULL,
    phone       TEXT NOT NULL UNIQUE CHECK (length(phone) = 10),
    category_id INTEGER
                REFERENCES repair_categories (category_id) ON DELETE SET NULL,
    hired_on    TEXT NOT NULL CHECK (date(hired_on) IS NOT NULL),
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE work_types (
    work_type_id INTEGER PRIMARY KEY,
    category_id  INTEGER NOT NULL
                 REFERENCES repair_categories (category_id) ON DELETE RESTRICT,
    name         TEXT NOT NULL UNIQUE,
    price_kop    INTEGER NOT NULL CHECK (price_kop >= 0),
    norm_hours   REAL NOT NULL CHECK (norm_hours > 0),
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE parts (
    part_id     INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL
                REFERENCES repair_categories (category_id) ON DELETE RESTRICT,
    article     TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    price_kop   INTEGER NOT NULL CHECK (price_kop >= 0),
    stock_qty   INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    min_qty     INTEGER NOT NULL DEFAULT 0 CHECK (min_qty >= 0)
);

CREATE TABLE orders (
    order_id             INTEGER PRIMARY KEY,
    car_id               INTEGER NOT NULL
                         REFERENCES cars (car_id) ON DELETE RESTRICT,
    employee_id          INTEGER NOT NULL
                         REFERENCES employees (employee_id) ON DELETE RESTRICT,
    accepted_at          TEXT NOT NULL
                         CHECK (datetime(accepted_at) IS NOT NULL),
    due_date             TEXT NOT NULL CHECK (date(due_date) IS NOT NULL),
    completed_at         TEXT,
    paid_at              TEXT,
    complaint            TEXT NOT NULL CHECK (length(complaint) >= 3),
    intake_mileage_km    INTEGER NOT NULL CHECK (intake_mileage_km >= 0),
    manual_discount_pct  INTEGER NOT NULL DEFAULT 0
                         CHECK (manual_discount_pct BETWEEN 0 AND 30),
    loyalty_discount_pct INTEGER NOT NULL DEFAULT 0
                         CHECK (loyalty_discount_pct IN (0, 5)),
    status               TEXT NOT NULL DEFAULT 'new'
                         CHECK (status IN ('new', 'in_progress', 'completed',
                                           'paid', 'cancelled')),
    CHECK (due_date >= date(accepted_at)),
    CHECK (paid_at IS NULL OR status = 'paid'),
    CHECK (status NOT IN ('completed', 'paid') OR completed_at IS NOT NULL)
);

CREATE TABLE order_works (
    order_work_id  INTEGER PRIMARY KEY,
    order_id       INTEGER NOT NULL
                   REFERENCES orders (order_id) ON DELETE CASCADE,
    work_type_id   INTEGER NOT NULL
                   REFERENCES work_types (work_type_id) ON DELETE RESTRICT,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_kop INTEGER NOT NULL CHECK (unit_price_kop >= 0)
);

CREATE TABLE order_parts (
    order_part_id  INTEGER PRIMARY KEY,
    order_id       INTEGER NOT NULL
                   REFERENCES orders (order_id) ON DELETE CASCADE,
    part_id        INTEGER NOT NULL
                   REFERENCES parts (part_id) ON DELETE RESTRICT,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_kop INTEGER NOT NULL CHECK (unit_price_kop >= 0),
    UNIQUE (order_id, part_id)
);

CREATE TABLE order_status_log (
    log_id     INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders (order_id) ON DELETE CASCADE,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    comment    TEXT
);
"""

_INDEXES = """
CREATE INDEX idx_cars_client ON cars (client_id);
CREATE INDEX idx_orders_car ON orders (car_id);
CREATE INDEX idx_orders_employee ON orders (employee_id);
CREATE INDEX idx_orders_status ON orders (status);
CREATE INDEX idx_orders_accepted ON orders (accepted_at);
CREATE INDEX idx_order_works_order ON order_works (order_id);
CREATE INDEX idx_order_parts_order ON order_parts (order_id);
CREATE INDEX idx_status_log_order ON order_status_log (order_id);
"""

# Сума замовлення рахується тут так само, як Order.total() у Python:
# знижка від суми кожного виду рядків, половина копійки — вгору.
_VIEWS = f"""
CREATE VIEW v_order_list AS
SELECT t.*,
       t.works_kop + t.parts_kop - t.discount_kop AS total_kop
FROM (
    SELECT o.order_id, o.car_id, o.employee_id, c.client_id,
           printf('АС-%06d', o.order_id) AS order_number,
           o.accepted_at, o.due_date, o.completed_at, o.paid_at, o.status,
           o.complaint, o.intake_mileage_km,
           o.manual_discount_pct, o.loyalty_discount_pct,
           c.plate_number, c.make, c.model,
           c.make || ' ' || c.model AS car_title,
           cl.last_name || ' ' || cl.first_name AS client_name,
           cl.phone AS client_phone,
           e.last_name || ' ' || e.first_name AS mechanic_name,
           s.works_kop, s.parts_kop, s.labor_hours,
           (s.works_kop * max(o.manual_discount_pct, o.loyalty_discount_pct)
               + 50) / 100
           + (s.parts_kop * o.manual_discount_pct + 50) / 100 AS discount_kop,
           CASE WHEN o.status IN ('new', 'in_progress')
                     AND o.due_date < date('now', 'localtime')
                THEN 1 ELSE 0 END AS is_overdue
    FROM orders o
    JOIN cars c ON c.car_id = o.car_id
    JOIN clients cl ON cl.client_id = c.client_id
    JOIN employees e ON e.employee_id = o.employee_id
    JOIN (
        SELECT o2.order_id,
               coalesce((SELECT sum(w.quantity * w.unit_price_kop)
                         FROM order_works w
                         WHERE w.order_id = o2.order_id), 0) AS works_kop,
               coalesce((SELECT sum(p.quantity * p.unit_price_kop)
                         FROM order_parts p
                         WHERE p.order_id = o2.order_id), 0) AS parts_kop,
               coalesce((SELECT round(sum(w.quantity * wt.norm_hours), 2)
                         FROM order_works w
                         JOIN work_types wt
                              ON wt.work_type_id = w.work_type_id
                         WHERE w.order_id = o2.order_id), 0) AS labor_hours
        FROM orders o2
    ) s ON s.order_id = o.order_id
) t;

CREATE VIEW v_client_list AS
SELECT cl.*,
       cl.last_name || ' ' || cl.first_name AS full_name,
       (SELECT count(*) FROM cars c WHERE c.client_id = cl.client_id)
           AS cars_count,
       (SELECT count(*) FROM orders o JOIN cars c ON c.car_id = o.car_id
        WHERE c.client_id = cl.client_id AND o.status = 'paid')
           AS paid_orders,
       EXISTS (SELECT 1 FROM orders o JOIN cars c ON c.car_id = o.car_id
               WHERE c.client_id = cl.client_id
                 AND o.status IN ('new', 'in_progress')) AS has_open_order,
       (SELECT count(*) FROM orders o JOIN cars c ON c.car_id = o.car_id
        WHERE c.client_id = cl.client_id AND o.status = 'paid')
           >= {LOYALTY_MIN_PAID_ORDERS} AS is_loyal
FROM clients cl;

CREATE VIEW v_car_list AS
SELECT c.*,
       cl.last_name || ' ' || cl.first_name AS owner_name,
       cl.phone AS owner_phone,
       (SELECT count(*) FROM orders o WHERE o.car_id = c.car_id)
           AS orders_count,
       (SELECT max(o.accepted_at) FROM orders o WHERE o.car_id = c.car_id)
           AS last_visit,
       EXISTS (SELECT 1 FROM orders o WHERE o.car_id = c.car_id
                 AND o.status IN ('new', 'in_progress')) AS has_open_order
FROM cars c
JOIN clients cl ON cl.client_id = c.client_id;

CREATE VIEW v_employee_list AS
SELECT e.*,
       e.last_name || ' ' || e.first_name AS full_name,
       rc.name AS category_name,
       (SELECT count(*) FROM orders o WHERE o.employee_id = e.employee_id
          AND o.status IN ('new', 'in_progress')) AS open_orders,
       (SELECT count(*) FROM orders o WHERE o.employee_id = e.employee_id)
           AS total_orders
FROM employees e
LEFT JOIN repair_categories rc ON rc.category_id = e.category_id;

CREATE VIEW v_work_type_list AS
SELECT wt.*, rc.name AS category_name,
       (SELECT count(*) FROM order_works w
        WHERE w.work_type_id = wt.work_type_id) AS times_used
FROM work_types wt
JOIN repair_categories rc ON rc.category_id = wt.category_id;

CREATE VIEW v_part_list AS
SELECT p.*, rc.name AS category_name,
       p.stock_qty < p.min_qty AS is_low
FROM parts p
JOIN repair_categories rc ON rc.category_id = p.category_id;

CREATE VIEW v_category_list AS
SELECT rc.*,
       (SELECT count(*) FROM work_types wt
        WHERE wt.category_id = rc.category_id) AS work_types_count,
       (SELECT count(*) FROM parts p
        WHERE p.category_id = rc.category_id) AS parts_count
FROM repair_categories rc;
"""


class SchemaManager:
    """Створює схему нової бази; версію зберігає в PRAGMA user_version.

    Версія 0 означає порожній файл. Після створення схеми версія стає
    SCHEMA_VERSION, тож повторний запуск програми нічого не змінює: дані не
    видаляються й демо-записи не дублюються.
    """

    SCHEMA_VERSION = 1

    def needs_creation(self, connection: sqlite3.Connection) -> bool:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == self.SCHEMA_VERSION:
            return False
        if version != 0:
            raise RuntimeError(
                f"Файл бази має невідому версію схеми {version}. "
                f"Видаліть його, щоб створити нову базу.")
        return True

    def create(self, connection: sqlite3.Connection):
        """Створює таблиці, індекси й представлення в поточній транзакції.

        З autocommit=False executescript() не підтверджує транзакцію сам,
        тому схема й демо-дані зберігаються разом або не зберігаються зовсім.
        """
        connection.executescript(_TABLES + _INDEXES + _VIEWS)
        connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
