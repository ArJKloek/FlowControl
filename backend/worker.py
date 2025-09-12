# top-level in dialogs.py
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import time
from collections.abc import Iterable
from propar import master as ProparMaster # your uploaded lib





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
                #dde_list = [24, 25, 129, 21, 170, 252]
                #params   = inst.db.get_parameters(dde_list)
                #values   = inst.read_parameters(params))
                dde_list = [205, 25]
                params   = self.inst.db.get_parameters(dde_list)
                values   = self.inst.read_parameters(params)
                for value in values:
                    print(value)
                value = None
                #value = values[0]
                #value = self.inst.readParameter(205)
                #name = self.inst.readParameter(25)
                #print(f'{self._node.port}, {self._node.address}, {value}') 
            except Exception:
                value = None
                name = None
            if value is not None:
                self._last_ok = value
                to_emit = value
            else:
                to_emit = self._last_ok

            #self.measured.emit(to_emit)
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
            # 1) write new fluid index (DDE 24)
            ok = inst.writeParameter(24, self.new_index)  # returns True/False
            if not ok:
                raise RuntimeError(f"Failed to write fluid index {self.new_index}")
                
            # 2) wait until the device has applied the new fluid
            #    condition: 24 == new_index AND 25 (name) is not empty
            import time
            deadline = time.time() + 5.0  # up to ~5s; most settle within <1s
            name = None
            while time.time() < deadline:
                try:
                    idx_now = inst.readParameter(24)
                    name    = inst.readParameter(25)  # string
                    if idx_now == self.new_index and name:
                        break
                except Exception:
                    pass
                time.sleep(0.15)

            # if still not confirmed, we’ll continue but expect some None fields
            time.sleep(0.2)  # tiny extra settle for property table

            # 3) read all properties (chained), then retry any that failed
            dde_list = [24, 25, 129, 21, 170, 252]
            params   = inst.db.get_parameters(dde_list)
            values   = inst.read_parameters(params)

            data, bad = {}, []
            for p, v in zip(params, values or []):
                status = v.get("status", 1)
                if status == 0:
                    data[p["dde_nr"]] = v["data"]
                else:
                    data[p["dde_nr"]] = None
                    bad.append(p["dde_nr"])

            # targeted retries (a couple of times) for stragglers
            for _ in range(3):
                if not bad:
                    break
                time.sleep(0.15)
                still_bad = []
                for dde in bad:
                    try:
                        val = inst.readParameter(dde)
                        data[dde] = val
                    except Exception:
                        still_bad.append(dde)
                bad = still_bad

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

