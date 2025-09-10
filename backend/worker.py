# top-level in dialogs.py
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import time

class MeasureWorker(QObject):
    measured = pyqtSignal(object)   # emits float or None
    finished = pyqtSignal()

    def __init__(self, manager, node, interval=0.5):
        super().__init__()
        self._manager = manager
        self._node = node
        self._interval = float(interval)
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                inst = self._manager.instrument(self._node.port, self._node.address)
                value = inst.measure   # you already use this in NodeViewer 
            except Exception:
                value = None
            self.measured.emit(value)
            time.sleep(self._interval)
        self.finished.emit()
