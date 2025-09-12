# top-level in dialogs.py
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import time
import propar
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
    
    def run(self):
        try:
            inst = self.manager.instrument(self.node.port, self.node.address)
            print(self.node.port, self.node.address, self.new_index)
            # 1) write new fluid index (DDE 24)
            ok = inst.writeParameter(24, self.new_index)  # returns True/False
            time.sleep(0.2)  # small settle after write

            # 2) chained read (use PARAM OBJECTS, not ints)
            dde_list = [24, 25, 129, 21, 170, 252]  # index, name, unit, capacity, density, viscosity
            params = inst.db.get_parameters(dde_list)              # build param dicts
            values = inst.read_parameters(params)                  # single chained read  

            data = {}
            bad = []
            for p, v in zip(params, values or []):
                status = v.get("status", 1)
                if status == 0:  # PP_STATUS_OK
                    data[p["dde_nr"]] = v["data"]
                else:
                    data[p["dde_nr"]] = None
                    bad.append((p["dde_nr"], status))

            # 3) fallback: retry failed ones individually
            if bad:
                for dde, _ in bad:
                    try:
                        data[dde] = inst.readParameter(dde)
                    except Exception:
                        pass

            out = {
                "index":     data.get(24),
                "name":      data.get(25),
                "unit":      data.get(129),
                "capacity":  data.get(21),
                "density":   data.get(170),
                "viscosity": data.get(252),
            }
            self.done.emit(out)
        except Exception as e:
            self.error.emit(str(e))

