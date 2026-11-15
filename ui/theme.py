"""Кольори інтерфейсу й застосування таблиці стилів."""

from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import QApplication

from config import RESOURCES_DIR

# Палітра в одному місці: QSS, делегати таблиць і графіки беруть кольори
# звідси, тож оформлення лишається узгодженим.
PALETTE = {
    "bg": "#F5F6F8",
    "surface": "#FFFFFF",
    "surface_alt": "#FAFBFC",
    "border": "#E2E5EA",
    "border_strong": "#CDD2DA",
    "text": "#1D2330",
    "muted": "#667085",
    "faint": "#98A2B3",
    "sidebar": "#1B2130",
    "sidebar_hover": "#232A3B",
    "sidebar_active": "#2A3245",
    "sidebar_text": "#AEB6C4",
    "accent": "#C2410C",
    "accent_hover": "#9A3412",
    "accent_bright": "#F97316",
    "accent_soft": "#FFEDD5",
    "accent_faint": "#FFF7ED",
    "danger": "#C92A2A",
    "danger_soft": "#FFF0F0",
    "success": "#2B8A3E",
    "success_soft": "#EBFBEE",
    "warning": "#B35C00",
    "warning_soft": "#FFF4D6",
}

# Кольори міток статусів замовлення: (текст, тло).
STATUS_COLORS = {
    "new": ("#1C64C2", "#E7F1FF"),
    "in_progress": ("#B35C00", "#FFF4D6"),
    "completed": ("#6741D9", "#F1EDFF"),
    "paid": ("#2B8A3E", "#EBFBEE"),
    "cancelled": ("#6B7380", "#F0F2F5"),
    "overdue": ("#C92A2A", "#FFF0F0"),
}

FONT_FAMILY = "Segoe UI"


def color(name: str) -> QColor:
    return QColor(PALETTE[name])


def apply_theme(app: QApplication):
    """Шрифт, стиль Fusion і таблиця стилів resources/style.qss.

    У файлі стилів кольори записано токенами @назва, щоб палітра була
    одна для QSS і для коду.
    """
    app.setStyle("Fusion")
    font = QFont(FONT_FAMILY, 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    qss = (RESOURCES_DIR / "style.qss").read_text(encoding="utf-8")
    icons = (RESOURCES_DIR / "icons").as_posix()
    qss = qss.replace("@icons", icons)
    # Довші назви замінюються першими, щоб @accent не зачепив @accent_soft.
    for name in sorted(PALETTE, key=len, reverse=True):
        qss = qss.replace(f"@{name}", PALETTE[name])
    app.setStyleSheet(qss)
