"""Графіки Matplotlib, вбудовані в інтерфейс PyQt5."""

import matplotlib

matplotlib.use("Qt5Agg")

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from services.report_service import ChartPoint  # noqa: E402
from ui.theme import FONT_FAMILY, PALETTE  # noqa: E402

matplotlib.rcParams["font.family"] = [FONT_FAMILY, "DejaVu Sans"]
matplotlib.rcParams["font.size"] = 9


def _grouped(value: float, _position=None) -> str:
    return f"{value:,.0f}".replace(",", " ")


class ChartCanvas(FigureCanvasQTAgg):
    """Полотно з одним графіком в оформленні застосунку."""

    def __init__(self, height: float = 3.2, parent=None):
        self.figure = Figure(figsize=(6, height), dpi=100,
                             facecolor=PALETTE["surface"])
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(int(height * 80))

    def _axes(self, title: str):
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.set_facecolor(PALETTE["surface"])
        axes.set_title(title, loc="left", fontsize=10.5, fontweight="bold",
                       color=PALETTE["text"], pad=12)
        for side in ("top", "right", "left"):
            axes.spines[side].set_visible(False)
        axes.spines["bottom"].set_color(PALETTE["border_strong"])
        axes.tick_params(colors=PALETTE["muted"], length=0)
        return axes

    def _empty(self, axes, text: str = "Немає даних за обраний період"):
        axes.set_xticks([])
        axes.set_yticks([])
        axes.spines["bottom"].set_visible(False)
        axes.text(0.5, 0.5, text, ha="center", va="center",
                  color=PALETTE["faint"], transform=axes.transAxes)
        self.draw_idle()

    def plot_columns(self, points: list[ChartPoint], title: str,
                     unit: str):
        """Вертикальні стовпці (наприклад, виручка по місяцях)."""
        axes = self._axes(title)
        if not any(point.value for point in points):
            self._empty(axes)
            return
        labels = [point.label for point in points]
        values = [point.value for point in points]
        bars = axes.bar(labels, values, color=PALETTE["accent_bright"],
                        width=0.6, zorder=3)
        axes.grid(axis="y", color=PALETTE["border"], zorder=0)
        axes.yaxis.set_major_formatter(FuncFormatter(_grouped))
        axes.set_ylabel(unit, color=PALETTE["muted"])
        for bar, value in zip(bars, values):
            if value:
                axes.annotate(_grouped(value), (bar.get_x()
                              + bar.get_width() / 2, bar.get_height()),
                              ha="center", va="bottom", fontsize=8,
                              color=PALETTE["muted"], xytext=(0, 3),
                              textcoords="offset points")
        axes.margins(y=0.15)
        self.figure.tight_layout()
        self.draw_idle()

    def plot_bars(self, points: list[ChartPoint], title: str, unit: str):
        """Горизонтальні стовпці (рейтинги): найбільше значення зверху."""
        axes = self._axes(title)
        if not points:
            self._empty(axes)
            return
        ordered = list(reversed(points))
        labels = [_short(point.label) for point in ordered]
        values = [point.value for point in ordered]
        bars = axes.barh(labels, values, color=PALETTE["accent_bright"],
                         height=0.6, zorder=3)
        axes.grid(axis="x", color=PALETTE["border"], zorder=0)
        axes.set_xlabel(unit, color=PALETTE["muted"])
        axes.xaxis.set_major_formatter(FuncFormatter(
            lambda value, _: f"{value:g}"))
        for bar, value in zip(bars, values):
            axes.annotate(f"{value:g}".replace(".", ","),
                          (bar.get_width(), bar.get_y()
                           + bar.get_height() / 2),
                          va="center", fontsize=8, color=PALETTE["muted"],
                          xytext=(4, 0), textcoords="offset points")
        axes.margins(x=0.12)
        self.figure.tight_layout()
        self.draw_idle()


def _short(text: str, limit: int = 30) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"
