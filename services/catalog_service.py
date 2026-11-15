"""Довідники: категорії ремонту, прайс робіт, склад запчастин."""

import sqlite3

from database import Equals, ListQuery
from models.catalog import Part, RepairCategory, WorkType
from services.base import AppService
from services.events import Topic

_CATEGORY_TOPICS = (Topic.CATALOG, Topic.STOCK, Topic.STAFF)
_WORK_TOPICS = (Topic.CATALOG,)
_PART_TOPICS = (Topic.STOCK, Topic.CATALOG)


class CatalogService(AppService):
    """Категорії, роботи й запчастини."""

    # ---- категорії ----------------------------------------------------------

    def categories(self) -> list[RepairCategory]:
        with self._unit() as uow:
            return uow.categories.all()

    def find_categories(self, query: ListQuery | None = None) \
            -> list[sqlite3.Row]:
        with self._unit() as uow:
            return uow.categories.find(query)

    def save_category(self, category: RepairCategory) -> int:
        def checks(uow):
            self._ensure_unique(uow.categories, "name", category.name,
                                category.category_id,
                                "Така категорія вже існує")
        return self._run_save("categories", category, "category_id", checks,
                              _CATEGORY_TOPICS)

    def delete_category(self, category_id: int):
        with self._unit() as uow:
            self._ensure_not_used(uow.categories, category_id, "Категорію")
            uow.categories.delete(category_id)
        self._notify(*_CATEGORY_TOPICS)

    # ---- прайс робіт --------------------------------------------------------

    def find_work_types(self, query: ListQuery | None = None) \
            -> list[sqlite3.Row]:
        with self._unit() as uow:
            return uow.work_types.find(query)

    def get_work_type(self, work_type_id: int) -> WorkType:
        with self._unit() as uow:
            return uow.work_types.get(work_type_id)

    def active_work_types(self) -> list[WorkType]:
        """Роботи, які можна додати до замовлення."""
        query = ListQuery(criteria=[Equals("is_active", 1)])
        with self._unit() as uow:
            return [uow.work_types.get(row["work_type_id"])
                    for row in uow.work_types.find(query)]

    def save_work_type(self, work_type: WorkType) -> int:
        def checks(uow):
            self._ensure_unique(uow.work_types, "name", work_type.name,
                                work_type.work_type_id,
                                "Робота з такою назвою вже є в прайсі")
        return self._run_save("work_types", work_type, "work_type_id",
                              checks, _WORK_TOPICS)

    def delete_work_type(self, work_type_id: int):
        with self._unit() as uow:
            self._ensure_not_used(
                uow.work_types, work_type_id, "Роботу",
                "Зніміть позначку «Активна», щоб прибрати її з нових "
                "замовлень.")
            uow.work_types.delete(work_type_id)
        self._notify(*_WORK_TOPICS)

    # ---- запчастини ---------------------------------------------------------

    def find_parts(self, query: ListQuery | None = None) -> list[sqlite3.Row]:
        with self._unit() as uow:
            return uow.parts.find(query)

    def get_part(self, part_id: int) -> Part:
        with self._unit() as uow:
            return uow.parts.get(part_id)

    def parts_in_stock(self) -> list[Part]:
        """Запчастини з ненульовим залишком — для додавання в замовлення."""
        with self._unit() as uow:
            return [uow.parts.get(row["part_id"])
                    for row in uow.parts.find() if row["stock_qty"] > 0]

    def save_part(self, part: Part) -> int:
        """Зберігає картку запчастини. Залишок наявної запчастини тут не
        змінюється — для цього є прихід і замовлення."""
        def checks(uow):
            self._ensure_unique(uow.parts, "article", part.article,
                                part.part_id,
                                "Запчастина з таким артикулом уже є")
        return self._run_save("parts", part, "part_id", checks, _PART_TOPICS)

    def receive_parts(self, part_id: int, quantity: int) -> Part:
        """Прихід запчастин на склад."""
        with self._unit() as uow:
            part = uow.parts.get(part_id)
            part.receive(quantity)
            uow.parts.update_stock(part)
        self._notify(Topic.STOCK)
        return part

    def delete_part(self, part_id: int):
        with self._unit() as uow:
            self._ensure_not_used(
                uow.parts, part_id, "Запчастину",
                "Вона є в історії замовлень; залиште її з нульовим "
                "залишком.")
            uow.parts.delete(part_id)
        self._notify(*_PART_TOPICS)
