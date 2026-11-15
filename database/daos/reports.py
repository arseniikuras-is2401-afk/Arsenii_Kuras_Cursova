"""Агрегатні запити для головної сторінки та статистики."""

import sqlite3
from datetime import date


class ReportDao:
    """Підсумкові показники з кількох таблиць. Лише читання."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def dashboard(self, today: date) -> dict:
        """Показники головної сторінки на дату `today`."""
        month_start = today.replace(day=1).isoformat()
        row = self._connection.execute(
            """
            SELECT
              sum(status IN ('new', 'in_progress')) AS open_orders,
              sum(status = 'in_progress') AS in_progress,
              sum(status IN ('new', 'in_progress')
                  AND due_date < :today) AS overdue,
              sum(status = 'completed') AS awaiting_payment,
              coalesce(sum(CASE WHEN status = 'paid'
                   AND date(paid_at) BETWEEN :month AND :today
                   THEN total_kop END), 0) AS revenue_month_kop,
              sum(status = 'paid'
                  AND date(paid_at) BETWEEN :month AND :today) AS paid_month
            FROM v_order_list
            """, {"today": today.isoformat(), "month": month_start}).fetchone()
        low_stock = self._connection.execute(
            "SELECT count(*) FROM parts WHERE stock_qty < min_qty"
        ).fetchone()[0]
        paid_month = row["paid_month"] or 0
        return {
            "open_orders": row["open_orders"] or 0,
            "in_progress": row["in_progress"] or 0,
            "overdue": row["overdue"] or 0,
            "awaiting_payment": row["awaiting_payment"] or 0,
            "revenue_month_kop": row["revenue_month_kop"],
            "paid_month": paid_month,
            "average_check_kop": (row["revenue_month_kop"] // paid_month
                                  if paid_month else 0),
            "low_stock": low_stock,
        }

    def overdue_orders(self, today: date,
                       limit: int = 20) -> list[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM v_order_list "
            "WHERE status IN ('new', 'in_progress') "
            "AND due_date < ? ORDER BY due_date LIMIT ?",
            (today.isoformat(), limit)).fetchall()

    def low_stock_parts(self, limit: int = 20) -> list[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM v_part_list WHERE is_low "
            "ORDER BY stock_qty - min_qty, name LIMIT ?", (limit,)).fetchall()

    def revenue_by_month(self, start: date, end: date,
                         employee_id: int | None = None) -> list[sqlite3.Row]:
        """Виручка оплачених замовлень по місяцях оплати."""
        return self._connection.execute(
            """
            SELECT strftime('%Y-%m', paid_at) AS month,
                   sum(total_kop) AS revenue_kop,
                   count(*) AS orders
            FROM v_order_list
            WHERE status = 'paid' AND date(paid_at) BETWEEN ? AND ?
              AND (? IS NULL OR employee_id = ?)
            GROUP BY month ORDER BY month
            """, (start.isoformat(), end.isoformat(), employee_id,
                  employee_id)).fetchall()

    def top_work_types(self, start: date, end: date, limit: int = 10,
                       employee_id: int | None = None) -> list[sqlite3.Row]:
        """Роботи, що трапляються в найбільшій кількості замовлень.

        Рахуються замовлення, а не штуки: інакше «балансування» (4 колеса
        в кожному замовленні) завжди було б першим.
        """
        return self._connection.execute(
            """
            SELECT wt.name, count(DISTINCT w.order_id) AS orders,
                   sum(w.quantity) AS quantity,
                   sum(w.quantity * w.unit_price_kop) AS amount_kop
            FROM order_works w
            JOIN orders o ON o.order_id = w.order_id
            JOIN work_types wt ON wt.work_type_id = w.work_type_id
            WHERE o.status IN ('completed', 'paid')
              AND date(o.completed_at) BETWEEN ? AND ?
              AND (? IS NULL OR o.employee_id = ?)
            GROUP BY wt.work_type_id
            ORDER BY orders DESC, amount_kop DESC
            LIMIT ?
            """, (start.isoformat(), end.isoformat(), employee_id,
                  employee_id, limit)).fetchall()

    def mechanic_load(self, start: date, end: date) -> list[sqlite3.Row]:
        """Нормо-години механіків у нескасованих замовленнях за період."""
        return self._connection.execute(
            """
            SELECT e.employee_id,
                   e.last_name || ' ' || e.first_name AS mechanic_name,
                   coalesce(sum(v.labor_hours), 0) AS labor_hours,
                   count(v.order_id) AS orders
            FROM employees e
            LEFT JOIN v_order_list v
                   ON v.employee_id = e.employee_id
                  AND v.status <> 'cancelled'
                  AND date(v.accepted_at) BETWEEN ? AND ?
            GROUP BY e.employee_id
            HAVING e.is_active = 1 OR count(v.order_id) > 0
            ORDER BY labor_hours DESC, mechanic_name
            """, (start.isoformat(), end.isoformat())).fetchall()

    def average_repair_days(self, start: date, end: date) -> float | None:
        """Середня тривалість ремонту: від початку робіт до завершення."""
        row = self._connection.execute(
            """
            SELECT avg(julianday(o.completed_at) - julianday(first_start))
            FROM orders o
            JOIN (SELECT order_id, min(changed_at) AS first_start
                  FROM order_status_log WHERE new_status = 'in_progress'
                  GROUP BY order_id) s ON s.order_id = o.order_id
            WHERE o.completed_at IS NOT NULL
              AND date(o.completed_at) BETWEEN ? AND ?
            """, (start.isoformat(), end.isoformat())).fetchone()
        return round(row[0], 1) if row[0] is not None else None
