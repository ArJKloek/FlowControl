# window_tiler.py
from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QGuiApplication

class DialogTiler:
    def __init__(self, margin=12, gap=12):
        self.margin = margin
        self.gap = gap
        self._next = None
        self._row_top = None
        self._row_h = 0

    def reset(self):
        self._next = None
        self._row_top = None
        self._row_h = 0

    def place(self, dlg):
        """Place dlg next to previous; wrap to next row if needed."""
        screen = QGuiApplication.screenAt(dlg.pos()) or QGuiApplication.primaryScreen()
        ag = screen.availableGeometry()
        if self._next is None:
            # start at top-left of the available area
            self._next = QPoint(ag.left() + self.margin, ag.top() + self.margin)
            self._row_top = self._next.y()
            self._row_h = 0

        # sizeHint is good before show; use actual size if already visible
        sz = dlg.sizeHint() if not dlg.isVisible() else dlg.size()
        w, h = sz.width(), sz.height()
        self._row_h = max(self._row_h, h)

        # wrap if it would overflow to the right
        if self._next.x() + w > ag.right() - self.margin:
            self._next = QPoint(ag.left() + self.margin, self._row_top + self._row_h + self.gap)
            self._row_top = self._next.y()
            self._row_h = h

        dlg.move(self._next)
        # advance cursor to the right for the next one
        self._next = QPoint(self._next.x() + w + self.gap, self._next.y())
