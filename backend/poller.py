# backend/poller.py
from PyQt5.QtCore import QObject, pyqtSignal
import heapq
import os
import queue
import random
import time
from propar_new import PP_STATUS_OK, PP_STATUS_TIMEOUT_ANSWER, pp_status_codes

FSETPOINT_DDE = 206     # fSetpoint
FMEASURE_DDE = 205      # fMeasure
FIDX_DDE = 24           # fluid index
FNAME_DDE = 25          # fluid name
SETPOINT_DDE = 9        # setpoint (int, 32000 100%)
MEASURE_DDE = 8         # measure (int, 32000 100%)
USERTAG_DDE = 115       # usertag 
IGNORE_TIMEOUT_ON_SETPOINT = False
MIN_SAFE_PERIOD = 0.5
DEFAULT_RESPONSE_TIMEOUT = 0.25
DEFAULT_SERIAL_TIMEOUT = 0.02
DIAG_INTERVAL_SEC = 10.0


class PortPoller(QObject):
    measured = pyqtSignal(object)       # emits {"port", "address", "data": {"fmeasure", "name"}, "ts"}
    error    = pyqtSignal(str)
    telemetry = pyqtSignal(object) 

    def __init__(self, manager, port, default_period=0.5):
        super().__init__()
        self.manager = manager
        self.port = port
        self.default_period = max(float(default_period), MIN_SAFE_PERIOD)
        self._running = True
        self._last_addr = None
        self._heap = []                 # (next_due, address, period)
        self._known = {}                # address -> (period)
        self._cmd_q = queue.Queue()     # serialize writes/one-off reads
        self._param_cache = {}          # NEW: address -> [param dicts]  ← avoid get_parameters() every time
        self._last_name = {}            
        self._diag_enabled = os.environ.get("FLOWCONTROL_DEBUG_PORT_DIAG", "").lower() in {"1", "true", "yes", "on"}
        self._diag = {
            "read_cycles": 0,
            "write_requests": 0,
            "timeouts": 0,
            "verify_failed": 0,
        }
        self._next_diag_ts = time.monotonic() + DIAG_INTERVAL_SEC

    def request_setpoint_flow(self, address: int, flow_value: float):
        """Queue a write of fSetpoint (engineering units) for this instrument."""
        self._cmd_q.put(("fset_flow", int(address), float(flow_value)))
    
    def request_setpoint_pct(self, address: int, pct_value: float):
        """Queue a write of Setpoint (percentage units) for this instrument."""
        self._cmd_q.put(("set_pct", int(address), float(pct_value)))

    def request_usertag(self, address: int, usertag: str):
        """Queue a write of Setpoint (percentage units) for this instrument."""
        self._cmd_q.put(("set_usertag", int(address), str(usertag)))

    def add_node(self, address, period=None):
        period = max(float(period or self.default_period), MIN_SAFE_PERIOD)
        if address in self._known:
            # Allow runtime period changes for already-registered nodes.
            self._known[address] = period
            heapq.heappush(self._heap, (time.monotonic() + 0.01, address, period))
            return
        # small staggering based on current count to avoid bursts
        t0 = time.monotonic() + (len(self._known) * 0.02)
        self._known[address] = period
        heapq.heappush(self._heap, (t0, address, period))

    def remove_node(self, address):
        self._known.pop(address, None)  # lazy removal: heap entries naturally expire

    # Optional: queue a command (executes on the same thread)
    def request_fluid_change(self, address, new_index):
        self._cmd_q.put(("fluid", address, int(new_index)))

    def stop(self):
        self._running = False

    def _status_code(self, res):
        if res is True:
            return PP_STATUS_OK
        if res is False:
            return None
        if isinstance(res, int):
            return res
        if isinstance(res, dict):
            return res.get("status")
        if isinstance(res, (list, tuple)):
            last = PP_STATUS_OK
            for x in res:
                if isinstance(x, dict):
                    st = x.get("status", 1)
                elif isinstance(x, int):
                    st = x
                else:
                    return None
                if st != PP_STATUS_OK:
                    return st
                last = st
            return last
        return None

    def _status_ok(self, res):
        return self._status_code(res) in (PP_STATUS_OK, 0)

    def _verify_readback(self, inst, dde, expected, tol=None):
        try:
            rb = inst.readParameter(dde)
        except Exception:
            return False, None

        if isinstance(expected, float):
            if not isinstance(rb, (int, float)):
                return False, rb
            abs_tol = tol if tol is not None else 1e-3 * max(1.0, abs(float(expected)))
            return abs(float(rb) - float(expected)) <= abs_tol, rb
        return rb == expected, rb

    def _write_with_timeout_retry_and_verify(self, inst, dde, value, verify_dde=None, tol=None):
        self._diag["write_requests"] += 1
        verify_target = verify_dde if verify_dde is not None else dde
        attempts = 2
        last_res = None
        last_rb = None

        for attempt in range(attempts):
            if attempt > 0:
                time.sleep(random.uniform(0.03, 0.09))

            last_res = inst.writeParameter(dde, value)
            if self._status_ok(last_res):
                return True, last_res, None

            code = self._status_code(last_res)
            if code == PP_STATUS_TIMEOUT_ANSWER:
                self._diag["timeouts"] += 1

            ok, rb = self._verify_readback(inst, verify_target, value, tol=tol)
            last_rb = rb
            if ok:
                return True, last_res, rb

            if code != PP_STATUS_TIMEOUT_ANSWER:
                break

        self._diag["verify_failed"] += 1
        return False, last_res, last_rb

    def _emit_diag_if_due(self):
        if not self._diag_enabled:
            return
        now = time.monotonic()
        if now < self._next_diag_ts:
            return
        self._next_diag_ts = now + DIAG_INTERVAL_SEC
        self.telemetry.emit({
            "ts": time.time(),
            "port": self.port,
            "address": None,
            "kind": "diag",
            "name": "port_counters",
            "value": dict(self._diag),
        })

    def run(self):
        inst_cache = {}
        FAIR_WINDOW = 0.005  # 5 ms window to consider multiple items "simultaneously due"

        while self._running:
            now = time.monotonic()
            self._emit_diag_if_due()

            # 1) (unchanged) handle 1 queued command...
            try:
                kind, address, arg = self._cmd_q.get_nowait()
            except queue.Empty:
                pass
            except Exception as e:
                self.error.emit(str(e))
            else:
                inst = inst_cache.get(address)
                if inst is None:
                    inst = self.manager.instrument(self.port, address)
                    inst_cache[address] = inst
                    inst.master.response_timeout = max(
                        getattr(inst.master, "response_timeout", DEFAULT_RESPONSE_TIMEOUT),
                        DEFAULT_RESPONSE_TIMEOUT,
                    )
                    try:
                        inst.master.propar.serial.timeout = max(
                            float(inst.master.propar.serial.timeout),
                            DEFAULT_SERIAL_TIMEOUT,
                        )
                    except Exception:
                        pass
                
                if kind == "fluid":
                    ok, res, _rb = self._write_with_timeout_retry_and_verify(
                        inst,
                        FIDX_DDE,
                        int(arg),
                        verify_dde=FIDX_DDE,
                    )
                    applied = ok
                    if applied:
                        deadline = time.monotonic() + 5.0
                        time.sleep(0.2)  # tiny settle
                        while time.monotonic() < deadline:
                            try:
                                idx_now = inst.readParameter(FIDX_DDE)
                                name_now = inst.readParameter(FNAME_DDE)
                                if idx_now == int(arg) and name_now:
                                    applied = True
                                    break
                            except Exception:
                                pass
                            time.sleep(0.15)
                    if applied:
                        # optional telemetry
                        self.telemetry.emit({
                            "ts": time.time(), "port": self.port, "address": address,
                            "kind": "fluid_change", "name": "fluid_index", "value": int(arg)
                        })
                    else:
                        code = self._status_code(res)
                        name = pp_status_codes.get(code, str(res))
                        self.error.emit(f"{self.port}/{address}: fluid change to {arg} not confirmed (res={res} {name})")
    
                elif kind == "fset_flow":
                    ok, res, rb = self._write_with_timeout_retry_and_verify(
                        inst,
                        FSETPOINT_DDE,
                        float(arg),
                        verify_dde=FSETPOINT_DDE,
                    )
                    if not ok and not (IGNORE_TIMEOUT_ON_SETPOINT and self._status_code(res) == PP_STATUS_TIMEOUT_ANSWER):
                        code = self._status_code(res)
                        name = pp_status_codes.get(code, str(res))
                        self.error.emit(f"{self.port}/{address}: setpoint write failed (res={res} {name}, rb={rb})")
                    self.telemetry.emit({
                        "ts": time.time(), "port": self.port, "address": address,
                        "kind": "setpoint", "name": "fSetpoint", "value": float(arg)
                    })
                
                elif kind == "set_pct":
                    ok, res, rb = self._write_with_timeout_retry_and_verify(
                        inst,
                        SETPOINT_DDE,
                        int(arg),
                        verify_dde=SETPOINT_DDE,
                        tol=1.0,
                    )
                    if not ok and not (IGNORE_TIMEOUT_ON_SETPOINT and self._status_code(res) == PP_STATUS_TIMEOUT_ANSWER):
                        code = self._status_code(res)
                        name = pp_status_codes.get(code, str(res))
                        self.error.emit(f"{self.port}/{address}: setpoint write failed (res={res} {name}, rb={rb})")
                    self.telemetry.emit({
                        "ts": time.time(), "port": self.port, "address": address,
                        "kind": "setpoint", "name": "Setpoint_pct", "value": int(arg)
                    })
                
                elif kind == "set_usertag":
                    ok, res, rb = self._write_with_timeout_retry_and_verify(
                        inst,
                        USERTAG_DDE,
                        str(arg),
                        verify_dde=USERTAG_DDE,
                    )
                    if not ok and not (IGNORE_TIMEOUT_ON_SETPOINT and self._status_code(res) == PP_STATUS_TIMEOUT_ANSWER):
                        code = self._status_code(res)
                        name = pp_status_codes.get(code, str(res))
                        self.error.emit(f"{self.port}/{address}: usertag write failed (res={res} {name}, rb={rb!r})")
                    self.telemetry.emit({
                        "ts": time.time(), "port": self.port, "address": address,
                        "kind": "set", "name": "Usertag", "value": str(arg)
                    })
            # 2) Fairly pick the next due instrument
            if not self._heap:
                time.sleep(0.1)
                continue

            due0, addr0, per0 = self._heap[0]
            sleep_for = max(0.0, due0 - now)
            if sleep_for > 0:
                time.sleep(min(sleep_for, 0.005))
                continue

            first = heapq.heappop(self._heap)  # (due0, addr0, per0)
            chosen = first

            # If the same address just ran AND another address is also due now, give the other a turn
            if self._heap:
                due1, addr1, per1 = self._heap[0]
                if (addr0 == self._last_addr) and ((due1 - now) <= FAIR_WINDOW):
                    chosen = heapq.heappop(self._heap)
                    heapq.heappush(self._heap, first)

            due, address, period = chosen

            # address might have been removed; skip if no longer known
            current_period = self._known.get(address)
            if current_period is None:
                continue
            if abs(float(current_period) - float(period)) > 1e-9:
                heapq.heappush(self._heap, (time.monotonic() + 0.01, address, float(current_period)))
                continue

            # 3) Do one read cycle (unchanged)
            try:
                inst = inst_cache.get(address)
                if inst is None:
                    inst = self.manager.instrument(self.port, address)
                    inst_cache[address] = inst
                    inst.master.response_timeout = max(
                        getattr(inst.master, "response_timeout", DEFAULT_RESPONSE_TIMEOUT),
                        DEFAULT_RESPONSE_TIMEOUT,
                    )
                    try:
                        inst.master.propar.serial.timeout = max(
                            float(inst.master.propar.serial.timeout),
                            DEFAULT_SERIAL_TIMEOUT,
                        )
                    except Exception:
                        pass

                params = self._param_cache.get(address)
                if params is None:
                    PARAMS = [FMEASURE_DDE, FNAME_DDE, MEASURE_DDE, SETPOINT_DDE, FSETPOINT_DDE]
                    params = inst.db.get_parameters(PARAMS)
                    self._param_cache[address] = params
                
                t0 = time.perf_counter()
                values = inst.read_parameters(params) or []
                self._diag["read_cycles"] += 1
                
                ok, data = {}, {}
                for p, v in zip(params, values):
                    dde = p["dde_nr"]
                    ok[dde] = (v.get("status") == 0 and v.get("data") is not None)
                    val = v.get("data")
                    if isinstance(val, str):
                        val = val.strip()
                    data[dde] = val


                # after building ok/data
                name_ok = ok.get(25)
                if name_ok:
                    self._last_name[address] = data[25]

                f_ok = ok.get(205)
                if f_ok:
                    # UI update (use last known name; may be None on first cycles)
                    self.measured.emit({
                        "port": self.port,
                        "address": address,
                        "data": {"fmeasure": float(data[205]), 
                        "name": self._last_name.get(address),
                        "measure": data.get(8),
                        "setpoint": data.get(9),
                        "fsetpoint": data.get(206)
                        },
                        "ts": time.time(),
                    })
                    
                    # Validate telemetry data before emitting to prevent extreme values from being logged
                    fmeasure_value = float(data[205])
                    if fmeasure_value >= 1000000.0:
                        # Log extreme value error to error logger (if manager has error_logger)
                        if hasattr(self.manager, 'error_logger'):
                            instrument_info = self.manager._get_instrument_info(self.port, address)
                            self.manager.error_logger.log_extreme_value_error(
                                port=self.port,
                                address=address,
                                extreme_value=fmeasure_value,
                                instrument_info=instrument_info
                            )
                    else:
                        # Only emit telemetry for normal values to keep logs clean
                        self.telemetry.emit({
                            "ts": time.time(), "port": self.port, "address": address,
                            "kind": "measure", "name": "fMeasure", "value": fmeasure_value
                        })
            except Exception as e:
                if "timeout" in str(e).lower():
                    self._diag["timeouts"] += 1
                self.error.emit(f"Poll error on {self.port}/{address}: {e}")

            # remember who we just serviced
            self._last_addr = address

            # 4) Reschedule drift-free (unchanged)
            next_due = due + float(current_period)
            while next_due <= time.monotonic():
                next_due += float(current_period)
            heapq.heappush(self._heap, (next_due, address, float(current_period)))
