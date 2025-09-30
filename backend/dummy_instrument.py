import math, time, random
from typing import List, Dict, Any

# DDE constants mirrored from poller expectations
FSETPOINT_DDE = 206
FMEASURE_DDE = 205
FIDX_DDE = 24
FNAME_DDE = 25
SETPOINT_DDE = 9
MEASURE_DDE = 8
USERTAG_DDE = 115
MODEL_DDE = 91
CAPACITY_DDE = 21
UNIT_DDE = 129

class _DummyDB:
    """Very small shim that mimics the subset of the real master/instrument DB API used.
    Real code calls db.get_parameter(dde) or db.get_parameters(list). We'll just return
    dicts with a 'dde_nr' to satisfy lookups.
    """
    def get_parameter(self, dde: int) -> Dict[str, Any]:
        return {"dde_nr": int(dde)}
    def get_parameters(self, ddes: List[int]) -> List[Dict[str, Any]]:
        return [self.get_parameter(d) for d in ddes]

class DummyInstrument:
    """Simulated Propar-like instrument for offline testing.
    Behaviour:
    - fMeasure (205) oscillates around setpoint with small noise.
    - setpoint can be written via fSetpoint (206) or percent (9) mapping 0..32000.
    - fluid index / name stable from a small table.
    - usertag stored and returned.
    """
    def __init__(self, port: str = "DUMMY0", address: int = 1):
        self.port = port
        self.address = int(address)
        self.db = _DummyDB()
        self._t0 = time.time()
        self._fset = 10.0  # engineering units
        self._pct_set = 16000  # 50%
        self._fluid_idx = 0
        self._fluid_names = ["AIR", "N2", "O2", "CO2"]
        self._usertag = "DUMMY"
        self._model = "SIM"  # DDE 91
        self._capacity = 100.0  # DDE 21
        self._unit = "ln/min"  # DDE 129

    # --- core single read ---
    def readParameter(self, dde: int):
        dde = int(dde)
        if dde == FMEASURE_DDE:
            return self._simulate_fmeasure()
        if dde == FSETPOINT_DDE:
            return float(self._fset)
        if dde == FIDX_DDE:
            return int(self._fluid_idx)
        if dde == FNAME_DDE:
            return self._fluid_names[self._fluid_idx]
        if dde == SETPOINT_DDE:
            return int(self._pct_set)
        if dde == MEASURE_DDE:
            # map engineering measure into 0..32000 scale
            return int(max(0, min(32000, (self._simulate_fmeasure() / self._capacity) * 32000)))
        if dde == USERTAG_DDE:
            return self._usertag
        if dde == MODEL_DDE:
            return self._model
        if dde == CAPACITY_DDE:
            return self._capacity
        if dde == UNIT_DDE:
            return self._unit
        return None

    def writeParameter(self, dde: int, value, verify=False, debug=False):  # mimic return True on success
        dde = int(dde)
        if dde == FSETPOINT_DDE:
            try:
                self._fset = float(value)
                # maintain percent form
                self._pct_set = int(max(0, min(32000, (self._fset / self._capacity) * 32000)))
                return True
            except Exception:
                return False
        if dde == SETPOINT_DDE:
            try:
                self._pct_set = int(value)
                self._fset = (self._pct_set / 32000.0) * self._capacity
                return True
            except Exception:
                return False
        if dde == FIDX_DDE:
            v = int(value)
            if 0 <= v < len(self._fluid_names):
                self._fluid_idx = v
                return True
            return False
        if dde == USERTAG_DDE:
            self._usertag = str(value)[:16]
            return True
        return False

    # --- batch read mimic inst.read_parameters([...]) returning list-of-dict ---
    def read_parameters(self, params: List[Dict[str, Any]]):
        out = []
        for p in params:
            dde = p.get("dde_nr")
            val = self.readParameter(dde)
            st = 0 if val is not None else 1
            out.append({"status": st, "data": val, "dde_nr": dde})
        return out

    # --- simulation helpers ---
    def _simulate_fmeasure(self):
        # smooth oscillation around setpoint + noise
        t = time.time() - self._t0
        base = self._fset + 0.5 * math.sin(t / 3.0)
        noise = random.uniform(-0.2, 0.2)
        return max(0.0, base + noise)

    # attributes accessed elsewhere (some code might look up .id, .measure)
    @property
    def id(self):
        return f"DUMMY-{self.address}"

    @property
    def measure(self):
        return self._simulate_fmeasure()
