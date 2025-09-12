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
        #self.inst = self._manager.instrument(self._node.port, self._node.address)
        self._last_ok = None

    def stop(self):
        self._running = False
    
    @staticmethod
    def _read_dde(master, address, dde_or_list):
        """
        Read one or many DDE parameters.
        - If `dde_or_list` is an int: returns the single value or None.
        - If it's an iterable of ints: returns {dde: value_or_None} using a chained read.
        """
        try:
            # ---- multiple DDEs (chained read) ----
            if isinstance(dde_or_list, Iterable) and not isinstance(dde_or_list, (str, bytes)):
                ddes = [int(d) for d in dde_or_list]
                params = []
                for d in ddes:
                    p = master.db.get_parameter(d)
                    p['node'] = address
                    params.append(p)
                res = master.read_parameters(params)  # list of dicts, same order as params
                out = {}
                for d, r in zip(ddes, res or []):
                    out[d] = r.get('data') if r and r.get('status', 1) == 0 else None
                return out

            # ---- single DDE ----
            d = int(dde_or_list)
            p = master.db.get_parameter(d)
            p['node'] = address
            res = master.read_parameters([p])
            if res and res[0].get('status', 1) == 0:
                return res[0]['data']
            return None

        except Exception:
            return None


    def run(self):
        while self._running:
            try:
                #dde_list = [24, 25, 129, 21, 170, 252]
                #params   = inst.db.get_parameters(dde_list)
                #values   = inst.read_parameters(params)
                vals = self._read_dde(self._node.port, self._node.address, [205, 24, 25, 129, 21, 170, 252])
                    #info.usertag, info.fluid, info.capacity, info.unit, orig_idx = (
                    #    vals.get(115), vals.get(25), vals.get(21), vals.get(129), vals.get(24)    
                    #)
                value = vals.get(205)    
                print(value)
                print(vals.get(24), vals.get(25), vals.get(129))
                #dde_list = [205,24, 25, 129, 21, 170, 252]
                #params   = self.inst.db.get_parameters(dde_list)
                
                #value = self.inst.readParameter(205)
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

