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
        self.inst = self._manager.instrument(self._node.port, self._node.address)
        self._last_ok = None

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                value = self.inst.readParameter(205)
                #print(f'{self._node.port}, {self._node.address}, {value}') 
            except Exception:
                value = None
            if value is not None:
                self._last_ok = value
                to_emit = value
            else:
                to_emit = self._last_ok

            self.measured.emit(to_emit)
            time.sleep(self._interval)
        self.finished.emit()
