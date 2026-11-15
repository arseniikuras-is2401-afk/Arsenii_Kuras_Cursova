"""Винятки предметної області з повідомленнями українською для користувача."""


class AutoServiceError(Exception):
    """Базовий виняток застосунку; текст пояснює причину користувачеві."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(AutoServiceError):
    """Некоректне значення поля.

    `field` вказує, яке поле підсвітити у формі.
    """

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


class BusinessRuleError(AutoServiceError):
    """Дія порушує правило предметної області."""


class InsufficientStockError(BusinessRuleError):
    """Запчастин на складі менше, ніж потрібно."""


class InvalidTransitionError(BusinessRuleError):
    """Недозволений перехід статусу замовлення."""


class RecordInUseError(BusinessRuleError):
    """Запис не можна видалити, бо на нього посилаються інші записи."""


class NotFoundError(AutoServiceError):
    """Запис не знайдено (наприклад, його вже видалено)."""
