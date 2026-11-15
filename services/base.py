"""Базовий клас сервісів: транзакції, годинник, сповіщення."""

from collections.abc import Callable
from datetime import date, datetime

from database import Database, UnitOfWork
from database.base_dao import TableDao
from models.errors import RecordInUseError, ValidationError
from services.events import EventHub, Topic

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    """Поточний час з точністю до хвилини (так зберігаються дати в базі)."""
    return datetime.now().replace(second=0, microsecond=0)


class AppService:
    """Спільне для сервісів.

    Кожна операція, що змінює дані: відкрити UnitOfWork → завантажити
    об'єкти → викликати методи моделей (вони перевіряють правила) → зберегти
    через DAO → commit → сповістити підписників.
    """

    def __init__(self, database: Database, events: EventHub,
                 clock: Clock = system_clock):
        self._database = database
        self._events = events
        self._clock = clock

    def _unit(self) -> UnitOfWork:
        return UnitOfWork(self._database)

    def _now(self) -> datetime:
        return self._clock()

    def _today(self) -> date:
        return self._clock().date()

    def _notify(self, *topics: Topic):
        self._events.publish(*topics)

    @staticmethod
    def _ensure_unique(dao: TableDao, column: str, value,
                       exclude_id: int | None, message: str):
        """Перевіряє унікальність до запиту, щоб назвати поле у формі."""
        if value is not None and dao.find_duplicate(column, value,
                                                    exclude_id):
            raise ValidationError(message, field=column)

    @staticmethod
    def _ensure_not_used(dao: TableDao, record_id: int, what: str,
                         advice: str = ""):
        """Пояснює, чому запис не можна видалити (RESTRICT у базі)."""
        usages = dao.usages(record_id)
        if usages:
            text = (f"{what} не можна видалити, бо є пов'язані записи "
                    f"({', '.join(usages)}).")
            raise RecordInUseError(f"{text} {advice}".strip())

    @staticmethod
    def _save_entity(dao: TableDao, entity, id_attribute: str) -> int:
        """Вставляє новий запис або оновлює наявний."""
        if getattr(entity, id_attribute) is None:
            return dao.insert(entity)
        dao.update(entity)
        return getattr(entity, id_attribute)

    def _run_save(self, dao_name: str, entity, id_attribute: str,
                  checks: Callable[[UnitOfWork], None],
                  topics: tuple[Topic, ...]) -> int:
        """Зберігає об'єкт після перевірок `checks` в одній транзакції.

        Якщо транзакція не вдасться, ідентифікатор нового об'єкта
        скидається в None, щоб повторне збереження знову було вставкою.
        """
        was_new = getattr(entity, id_attribute) is None
        try:
            with self._unit() as uow:
                checks(uow)
                record_id = self._save_entity(getattr(uow, dao_name), entity,
                                              id_attribute)
        except Exception:
            if was_new:
                setattr(entity, id_attribute, None)
            raise
        self._notify(*topics)
        return record_id
