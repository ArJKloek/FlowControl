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
        # Add test variables for extreme value simulation
        self._extreme_test_enabled = False
        self._extreme_test_counter = 0
        self._extreme_test_interval = 20  # Generate extreme value every 20 measurements
        # Provide a stub 'master' with attributes used by poller
        class _StubSerial:
            def __init__(self):
                self.timeout = 0.005
        class _StubPropar:
            def __init__(self):
                self.serial = _StubSerial()
        class _StubMaster:
            def __init__(self):
                self.response_timeout = 0.08
                self.propar = _StubPropar()
        self.master = _StubMaster()

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
                old_fset = getattr(self, "_fset", float(value))
                self._fset = float(value)
                self._setpoint_transition_start = time.time()
                self._setpoint_transition_from = getattr(self, "_last_meas_value", old_fset)
                self._setpoint_transition_to = self._fset
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

    def enable_extreme_test(self, enabled: bool = True, interval: int = 20):
        """Enable/disable extreme value testing to validate flow capping.
        
        Args:
            enabled: Whether to enable extreme value generation
            interval: How often to generate extreme values (every N measurements)
        """
        self._extreme_test_enabled = enabled
        self._extreme_test_interval = interval
        self._extreme_test_counter = 0

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
        # Only update value every 300ms to simulate real device timing
        now = time.time()
        if not hasattr(self, "_last_meas_update"):
            self._last_meas_update = 0.0
            self._last_meas_value = self._fset
        # Smooth transition to new setpoint over ~1s
        transition_time = 1.0
        if hasattr(self, "_setpoint_transition_start"):
            elapsed = now - self._setpoint_transition_start
            if elapsed < transition_time:
                # Linear interpolation
                frac = min(1.0, elapsed / transition_time)
                target = (1-frac)*self._setpoint_transition_from + frac*self._setpoint_transition_to
            else:
                target = self._setpoint_transition_to
                # Remove transition attributes after done
                del self._setpoint_transition_start
                del self._setpoint_transition_from
                del self._setpoint_transition_to
        else:
            target = self._fset
        if (now - self._last_meas_update) >= 0.1:  # Reduced from 0.9 to 0.1 for testing
            self._extreme_test_counter += 1
            
            # Check if we should generate an extreme value for testing
            if (self._extreme_test_enabled and 
                self._extreme_test_counter >= self._extreme_test_interval):
                self._extreme_test_counter = 0
                # Generate extreme value (10^7 like the real error you encountered)
                extreme_value = 1.0e7
                self._last_meas_value = extreme_value
                self._last_meas_update = now
                return extreme_value
            
            # Normal simulation
            t = now - self._t0
            base = target + 0.2 * math.sin(t / 3.0)
            # Reduce noise amplitude and apply smoothing
            noise = random.uniform(-0.005, 0.005)
            raw_value = max(0.0, base + noise)
            # Simple exponential smoothing for realism
            alpha = 0.3
            prev = getattr(self, "_last_meas_value", raw_value)
            smoothed = alpha * raw_value + (1 - alpha) * prev
            self._last_meas_value = smoothed
            self._last_meas_update = now
        return self._last_meas_value

    # attributes accessed elsewhere (some code might look up .id, .measure)
    @property
    def id(self):
        return f"DUMMY-{self.address}"

    @property
    def measure(self):
        return self._simulate_fmeasure()
