"""Міст між подіями сервісів і сигналами Qt."""

from PyQt5.QtCore import QObject, pyqtSignal

from services.events import EventHub, Topic


class QtEventBridge(QObject):
    """Підписується на EventHub і перетворює події на Qt-сигнал.

    Сервіси нічого не знають про Qt, а віджети отримують звичайний сигнал
    changed(frozenset[Topic]) і оновлюються в головному потоці.
    """

    changed = pyqtSignal(object)

    def __init__(self, hub: EventHub, parent=None):
        super().__init__(parent)
        self._hub = hub
        hub.subscribe(list(Topic), self._on_hub_event)

    def _on_hub_event(self, topics: frozenset):
        self.changed.emit(topics)

    def detach(self):
        self._hub.unsubscribe(self._on_hub_event)
