# backend/poller.py
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import time, heapq, queue
from propar_new import PP_STATUS_OK, PP_STATUS_TIMEOUT_ANSWER, pp_status_codes

FSETPOINT_DDE = 206     # fSetpoint
FMEASURE_DDE = 205      # fMeasure
FIDX_DDE = 24           # fluid index
FNAME_DDE = 25          # fluid name
SETPOINT_DDE = 9        # setpoint (int, 32000 100%)
MEASURE_DDE = 8         # measure (int, 32000 100%)
USERTAG_DDE = 115       # usertag
CAPACITY_DDE = 21       # capacity (float)
TYPE_DDE = 90           # type (string)
IDENT_NR_DDE = 175      # identification number (device type code)
IGNORE_TIMEOUT_ON_SETPOINT = False


class PortPoller(QObject):
    measured = pyqtSignal(object)       # emits {"port", "address", "data": {"fmeasure", "name"}, "ts"}
    error    = pyqtSignal(str)
    telemetry = pyqtSignal(object) 

    def __init__(self, manager, port, default_period=0.5):
        super().__init__()
        self.manager = manager
        self.port = port
        self.default_period = float(default_period)
        self._running = True
        self._last_addr = None
        self._heap = []                 # (next_due, address, period)
        self._known = {}                # address -> (period)
        self._cmd_q = queue.Queue()     # serialize writes/one-off reads
        self._param_cache = {}          # NEW: address -> [param dicts]  ← avoid get_parameters() every time
        self._last_name = {}
        # Add small delay for shared USB devices to reduce contention
        self._last_operation_time = 0            

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
        period = float(period or self.default_period)
        if address in self._known:
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

    def run(self):
        # Use manager's shared cache instead of local cache for better USB device coordination
        FAIR_WINDOW = 0.005  # 5 ms window to consider multiple items "simultaneously due"

        while self._running:
            now = time.monotonic()

            # 1) (unchanged) handle 1 queued command...
            try:
                kind, address, arg = self._cmd_q.get_nowait()
            except queue.Empty:
                pass
            except Exception as e:
                self.error.emit(str(e))
            else:
                # Use shared instrument with proper locking for USB device coordination
                inst = self.manager.get_shared_instrument(self.port, address)
                
                if kind == "fluid":
                    old_rt = getattr(inst.master, "response_timeout", 0.5)
                    try:
                        # fluid switches can take longer; give the write a bit more time
                        inst.master.response_timeout = max(old_rt, 0.8)
                        res = inst.writeParameter(FIDX_DDE, int(arg), verify=True, debug=True)
                    finally:
                        inst.master.response_timeout = old_rt
                    
                    # Normalize immediate result
                    ok_immediate = (
                        res is True or res == PP_STATUS_OK or res == 0 or
                        (isinstance(res, dict) and res.get("status", 1) in (0, PP_STATUS_OK))
                    )
                    # If it timed out (25) or wasn't clearly OK, do a read-back verify.
                    applied = ok_immediate
                    if not ok_immediate or res == PP_STATUS_TIMEOUT_ANSWER:    
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
                        name = pp_status_codes.get(res, str(res))
                        self.error.emit(f"{self.port}/{address}: fluid change to {arg} not confirmed (res={res} {name})")
    
                elif kind == "fset_flow":
                    # slightly higher timeout for writes (still much lower than 0.5s default)
                    old_rt = getattr(inst.master, "response_timeout", 0.5)
                    try:
                        inst.master.response_timeout = max(old_rt, 0.20)
                        res = inst.writeParameter(FSETPOINT_DDE, float(arg))
                    finally:
                        inst.master.response_timeout = old_rt

                    # normalize “immediate OK”
                    ok_immediate = (
                        (res is True) or
                        (res == PP_STATUS_OK) or
                        (isinstance(res, dict) and res.get("status") == PP_STATUS_OK)
                    )

                    if ok_immediate:
                        # great — nothing else to do
                        pass
                    elif res == PP_STATUS_TIMEOUT_ANSWER:
                        # timed out waiting for ACK; either verify or (optionally) ignore
                        if IGNORE_TIMEOUT_ON_SETPOINT:
                            # do nothing: treat as success
                            pass
                        else:
                            # verify by reading back
                            try:
                                rb = inst.readParameter(FSETPOINT_DDE)
                            except Exception:
                                rb = None
                            ok = False
                            if isinstance(rb, (int, float)):
                                tol = 1e-3 * max(1.0, abs(float(arg)))
                                ok = abs(float(rb) - float(arg)) <= tol
                            if not ok:
                                name = pp_status_codes.get(res, str(res))
                                self.error.emit(f"{self.port}/{address}: setpoint write timeout; verify failed (res={res} {name}, rb={rb})")
                    else:
                        # some other status → report
                        name = pp_status_codes.get(res, str(res))
                        self.error.emit(f"{self.port}/{address}: setpoint write status {res} ({name})")
                    self.telemetry.emit({
                        "ts": time.time(), "port": self.port, "address": address,
                        "kind": "setpoint", "name": "fSetpoint", "value": float(arg)
                    })
                
                elif kind == "set_pct":
                    # slightly higher timeout for writes (still much lower than 0.5s default)
                    old_rt = getattr(inst.master, "response_timeout", 0.5)
                    try:
                        inst.master.response_timeout = max(old_rt, 0.20)
                        res = inst.writeParameter(SETPOINT_DDE, int(arg))
                    finally:
                        inst.master.response_timeout = old_rt

                    # normalize “immediate OK”
                    ok_immediate = (
                        (res is True) or
                        (res == PP_STATUS_OK) or
                        (isinstance(res, dict) and res.get("status") == PP_STATUS_OK)
                    )

                    if ok_immediate:
                        # great — nothing else to do                        
                        pass
                    elif res == PP_STATUS_TIMEOUT_ANSWER:
                        # timed out waiting for ACK; either verify or (optionally) ignore
                        if IGNORE_TIMEOUT_ON_SETPOINT:
                            # do nothing: treat as success
                            pass
                        else:
                            # verify by reading back
                            try:
                                rb = inst.readParameter(SETPOINT_DDE)
                            except Exception:
                                rb = None
                            ok = False
                            if isinstance(rb, (int, int)):
                                tol = 1e-3 * max(1.0, abs(int(arg)))
                                ok = abs(int(rb) - float(arg)) <= tol
                            if not ok:
                                name = pp_status_codes.get(res, str(res))
                                self.error.emit(f"{self.port}/{address}: setpoint write timeout; verify failed (res={res} {name}, rb={rb})")
                    else:
                        # some other status → report
                        name = pp_status_codes.get(res, str(res))
                        self.error.emit(f"{self.port}/{address}: setpoint write status {res} ({name})")
                    self.telemetry.emit({
                        "ts": time.time(), "port": self.port, "address": address,
                        "kind": "setpoint", "name": "Setpoint_pct", "value": int(arg)
                    })
                
                elif kind == "set_usertag":
                    # slightly higher timeout for writes (still much lower than 0.5s default)
                    old_rt = getattr(inst.master, "response_timeout", 0.5)
                    try:
                        inst.master.response_timeout = max(old_rt, 0.20)
                        #tag_out = _norm_str(arg)
                        res = inst.writeParameter(USERTAG_DDE, str(arg))

                    finally:
                        inst.master.response_timeout = old_rt

                    # normalize “immediate OK”
                    ok_immediate = (
                        (res is True) or
                        (res == PP_STATUS_OK) or
                        (isinstance(res, dict) and res.get("status") == PP_STATUS_OK)
                    )

                    if ok_immediate:
                        # great — nothing else to do                        
                        pass
                    elif res == PP_STATUS_TIMEOUT_ANSWER:
                        # timed out waiting for ACK; either verify or (optionally) ignore
                        if IGNORE_TIMEOUT_ON_SETPOINT:
                            # do nothing: treat as success
                            pass
                        else:
                            # verify by reading back
                            try:
                                rb = inst.readParameter(USERTAG_DDE)
                            except Exception:
                                rb = None
                            
                            ok = rb == str(arg)
                            if not ok:
                                name = pp_status_codes.get(
                                res if isinstance(res, int) else (res.get("status") if isinstance(res, dict) else None),
                                str(res)
                                )
                                self.error.emit(
                                f"{self.port}/{address}: usertag write timeout; verify failed (res={res} {name}, rb={arg!r})"
                                )
                    else:
                        # some other status → report
                        name = pp_status_codes.get(res, str(res))
                        self.error.emit(f"{self.port}/{address}: setpoint write status {res} ({name})")
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
            if address not in self._known:
                continue

            # 3) Do one read cycle with shared instrument cache for USB coordination
            try:
                # Add small delay for shared USB devices to reduce contention
                current_time = time.time()
                time_since_last = current_time - self._last_operation_time
                min_interval = 0.001  # 1ms minimum between operations on same port
                if time_since_last < min_interval:
                    time.sleep(min_interval - time_since_last)
                
                # Use shared instrument with proper locking for USB device coordination
                inst = self.manager.get_shared_instrument(self.port, address)
                
                self._last_operation_time = time.time()

                params = self._param_cache.get(address)
                if params is None:
                    PARAMS = [FMEASURE_DDE, FNAME_DDE, MEASURE_DDE, SETPOINT_DDE, FSETPOINT_DDE, CAPACITY_DDE, IDENT_NR_DDE]
                    params = inst.db.get_parameters(PARAMS)
                    self._param_cache[address] = params
                
                t0 = time.perf_counter()
                values = inst.read_parameters(params) or []
                
                ok, data = {}, {}
                for p, v in zip(params, values):
                    dde = p["dde_nr"]
                    ok[dde] = (v.get("status") == 0 and v.get("data") is not None)
                    val = v.get("data")
                    if isinstance(val, str):
                        val = val.strip()
                    data[dde] = val


                # after building ok/data
                name_ok = ok.get(FNAME_DDE)
                if name_ok:
                    self._last_name[address] = data[FNAME_DDE]

                f_ok = ok.get(FMEASURE_DDE)

                if f_ok:
                    # Get values for validation
                    fmeasure_value = data.get(FMEASURE_DDE)
                    capacity_value = data.get(CAPACITY_DDE)
                    ident_nr = data.get(IDENT_NR_DDE)
                    
                    # Validate FMEASURE against CAPACITY (skip if > 150% of capacity)
                    # Only apply validation to DMFC instruments (ident_nr == 7)
                    skip_measurement = False
                    if (ident_nr == 7 and  # Only for DMFC instruments
                        capacity_value is not None and fmeasure_value is not None):
                        try:
                            capacity_150_percent = float(capacity_value) * 1.5
                            if float(fmeasure_value) > capacity_150_percent:
                                skip_measurement = True
                                print(f"⚠️  {self.port}/{address}: DMFC validation - Skipping measurement - FMEASURE ({fmeasure_value:.3f}) exceeds 150% of capacity ({capacity_150_percent:.3f})")
                        except (ValueError, TypeError):
                            # If conversion fails, continue with measurement
                            pass
                    
                    if skip_measurement:
                        # Skip this measurement cycle, don't emit measured signal
                        # Emit telemetry for the skipped measurement (DMFC only)
                        self.telemetry.emit({
                            "ts": time.time(), 
                            "port": self.port, 
                            "address": address,
                            "kind": "validation_skip", 
                            "name": "dmfc_capacity_exceeded", 
                            "value": float(fmeasure_value) if fmeasure_value is not None else 0.0,
                            "capacity": float(capacity_value) if capacity_value is not None else 0.0,
                            "threshold": capacity_150_percent,
                            "device_type": "DMFC",
                            "reason": f"DMFC validation: FMEASURE ({fmeasure_value:.3f}) > 150% capacity ({capacity_150_percent:.3f})"
                        })
                        pass
                    else:
                        # Determine device category based on identification number
                        device_category = "UNKNOWN"
                        if ident_nr == 7:
                            device_category = "DMFC"  # Digital Mass Flow Controller
                        elif ident_nr == 8:
                            device_category = "DMFM"  # Digital Mass Flow Meter
                        elif ident_nr == 12:
                            device_category = "DLFC"  # Digital Liquid Flow Controller  
                        elif ident_nr == 13:
                            device_category = "DLFM"  # Digital Liquid Flow Meter
                        elif ident_nr == 9:
                            device_category = "DEPC"  # Digital Electronic Pressure Controller
                        elif ident_nr == 10:
                            device_category = "DEPM"  # Digital Electronic Pressure Meter

                        # UI update (use last known name; may be None on first cycles)
                        self.measured.emit({
                            "port": self.port,
                            "address": address,
                            "data": {"fmeasure": float(data[FMEASURE_DDE]) if data.get(FMEASURE_DDE) is not None else 0.0, 
                            "name": self._last_name.get(address),
                            "measure": data.get(MEASURE_DDE),
                            "setpoint": data.get(SETPOINT_DDE),
                            "fsetpoint": data.get(FSETPOINT_DDE),
                            "capacity": data.get(CAPACITY_DDE),
                            "device_category": device_category,
                            "ident_nr": ident_nr,
                            },
                            "ts": time.time(),
                        })
                    # telemetry does not need the name at all
                    fmeasure_val = data.get(FMEASURE_DDE)
                    if fmeasure_val is not None:
                        self.telemetry.emit({
                            "ts": time.time(), "port": self.port, "address": address,
                            "kind": "measure", "name": "fMeasure", "value": float(fmeasure_val)
                        })
            except Exception as e:
                # Enhanced error handling with specific error types
                error_msg = str(e)
                error_type = "communication"
                
                # Classify error types for better handling
                if "port that is not open" in error_msg.lower():
                    error_type = "port_closed"
                    # Clear the shared instrument cache for this address to force reconnection
                    self.manager.clear_shared_instrument_cache(self.port, address)
                elif "timeout" in error_msg.lower():
                    error_type = "timeout"
                elif "permission denied" in error_msg.lower() or "access denied" in error_msg.lower():
                    error_type = "permission_denied"
                elif "device not found" in error_msg.lower() or "no such file" in error_msg.lower():
                    error_type = "device_not_found"
                
                self.error.emit(f"Poll error on {self.port}/{address}: {e} (type: {error_type})")

            # remember who we just serviced
            self._last_addr = address

            # 4) Reschedule drift-free (unchanged)
            next_due = due + period
            while next_due <= time.monotonic():
                next_due += period
            heapq.heappush(self._heap, (next_due, address, period))
