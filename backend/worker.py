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

class FluidApplyWorker(QObject):
    done = pyqtSignal(dict)      # emits {"index", "name", "unit", "capacity", "density", "viscosity"}
    error = pyqtSignal(str)

    def __init__(self, manager, node, new_index):
        super().__init__()
        self.manager = manager
        self.node = node
        self.new_index = int(new_index)
        print(self.new_index)
    def run(self):
        try:
            inst = self.manager.instrument(self.node.port, self.node.address)  # same pattern you use elsewhere 
            # write new fluid index (DDE 24), then read back fresh values
            ok = inst.writeParameter(24, self.new_index)
            if not ok:
                self.error.emit("Instrument rejected fluid index.")
                return
            time.sleep(0.05)  # tiny settle
            out = {
                "index":     inst.readParameter(24),
                "name":      inst.readParameter(25),   # fluid name
                "unit":      inst.readParameter(129),  # engineering unit
                "capacity":  inst.readParameter(21),   # max flow/capacity
                "density":   inst.readParameter(170),
                "viscosity": inst.readParameter(252),
            }
            self.done.emit(out)
        except Exception as e:
            self.error.emit(str(e))
