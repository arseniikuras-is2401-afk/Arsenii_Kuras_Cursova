"""Лінійні піктограми, намальовані вручну у форматі SVG.

Власні прості контури замість сторонніх наборів: немає залежностей і
питань ліцензії, а колір піктограми можна змінити під тему.
"""

from functools import lru_cache

from PyQt5.QtCore import QByteArray, QRectF, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

_PATHS = {
    "home": '<path d="M3 11l9-7 9 7"/><path d="M5.5 9.5V20h13V9.5"/>'
            '<path d="M10 20v-5h4v5"/>',
    "orders": '<rect x="5" y="4" width="14" height="17" rx="2"/>'
              '<path d="M9 3h6v3H9z"/><path d="M9 11h6M9 15h6M9 19h3"/>',
    "clients": '<circle cx="12" cy="8" r="3.6"/>'
               '<path d="M4.5 20.5c.8-3.8 3.9-5.8 7.5-5.8s6.7 2 7.5 5.8"/>',
    "car": '<path d="M4 16.5v-4.2L6.2 7h11.6l2.2 5.3v4.2z"/>'
           '<path d="M4 12.3h16"/><circle cx="8" cy="16.5" r="1.7"/>'
           '<circle cx="16" cy="16.5" r="1.7"/>',
    "staff": '<path d="M14.7 6.3a4 4 0 0 0 5 5L11 20a2.1 2.1 0 0 1-3-3'
             'l8.7-8.7a4 4 0 0 0-2-2z"/>',
    "price": '<path d="M3.5 12.5V4.5h8l9 9-8 8z"/>'
             '<circle cx="8" cy="9" r="1.4"/>',
    "stock": '<path d="M3.5 7.5L12 3.5l8.5 4v9L12 20.5l-8.5-4z"/>'
             '<path d="M3.5 7.5L12 11.5l8.5-4M12 11.5v9"/>',
    "chart": '<path d="M4 20V11M10 20V5M16 20v-6M3 20.5h18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="6"/>'
              '<path d="M19.5 19.5L15.5 15.5"/>',
    "reset": '<path d="M4.5 12a7.5 7.5 0 1 0 2.3-5.4"/><path d="M4.5 4v4h4"/>',
    "export": '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 20h14"/>',
    "import": '<path d="M12 15V4M7.5 8.5L12 4l4.5 4.5M5 20h14"/>',
    "trash": '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/>',
    "edit": '<path d="M4.5 19.5h4l10-10-4-4-10 10z"/><path d="M13 7l4 4"/>',
    "open": '<path d="M14 4.5h5.5V10M19.5 4.5L11 13"/>'
            '<path d="M17.5 14v5.5h-13v-13H10"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v6"/>'
            '<path d="M12 7.6v.4"/>',
    "receive": '<path d="M3.5 7.5L12 3.5l8.5 4v9L12 20.5l-8.5-4z"/>'
               '<path d="M12 8v7M8.8 11.8L12 15l3.2-3.2"/>',
    "power": '<path d="M12 3.5v8"/><path d="M7 6.5a7 7 0 1 0 10 0"/>',
    "wrench_logo": '<path d="M14.7 6.3a4 4 0 0 0 5 5L11 20a2.1 2.1 0 0 1-3-3'
                   'l8.7-8.7a4 4 0 0 0-2-2z"/>',
}

_TEMPLATE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
             'fill="none" stroke="{color}" stroke-width="{width}" '
             'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


@lru_cache(maxsize=None)
def icon(name: str, color: str = "#4A5466", size: int = 18,
         width: float = 1.8) -> QIcon:
    """Піктограма потрібного кольору; з кешем, бо малюється однаково."""
    svg = _TEMPLATE.format(color=color, width=width, body=_PATHS[name])
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    result = QIcon()
    for scale in (1, 2):   # звичайний і HiDPI екрани
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        result.addPixmap(pixmap)
    return result
