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
            inst = self.manager.instrument(self.node.port, self.node.address)  # same pattern you use elsewhere 
            # write new fluid index (DDE 24), then read back fresh values
            ok = inst.writeParameter(24, self.new_index)
            #if not ok:
            #    self.error.emit("Instrument rejected fluid index.")
            #    return
            time.sleep(0.6)  # tiny settle
            # Parameters to read: Fluidset index, 25=name, 129=unit, 21=capacity, 170=density, 252=viscosity
            # Process and fbnnr

            # Choose the DDE parameters you want to read in a single chained call
            dde_list = [24, 25, 129, 21, 170, 252]  # measure, setpoint, capacity, fluid index/name, unit, density, viscosity, usertag

            # Build parameter objects from the DB (handles proc/parm/type for you)
            params = inst.db.get_parameters(dde_list)
            values = inst.read_parameters(params)       # single chained read

            
            # Read them in one go
            #values = inst.read_parameters(dde_list)  # list of dicts: each has 'dde_nr' (via driver), 'data', 'status', etc.
            # Convert to a dict keyed by DDE nr for convenience
            #print(values)
            #result = {v.get('dde_nr', p.get('dde_nr', None)): v['data'] for v, p in zip(values, params)}
            #print(result)
            
            #out = {
            #    "index":     inst.readParameter(24),
            #    "name":      inst.readParameter(25),   # fluid name
            #    "unit":      inst.readParameter(129),  # engineering unit
            #    "capacity":  inst.readParameter(21),   # max flow/capacity
            #    "density":   inst.readParameter(170),
            #    "viscosity": inst.readParameter(252),
            #}
            #self.done.emit(out)

             # 3) map results by DDE number (None on error)
            read = {}
            for p, v in zip(params, values):
                read[p['dde_nr']] = v['data'] if v.get('status', 0) == 0 else None

            out = {
                "index":     read.get(24),
                "name":      read.get(25),
                "unit":      read.get(129),
                "capacity":  read.get(21),
                "density":   read.get(170),
                "viscosity": read.get(252),
            }
            self.done.emit(out)
        except Exception as e:
            self.error.emit(str(e))
