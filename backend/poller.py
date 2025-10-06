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
    error_occurred = pyqtSignal(str)    # emits error messages for connection failures 

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
                        # Enhanced safe conversion for fluid index
                        try:
                            safe_arg = int(arg) if arg not in (None, "", " ") else 0
                        except (ValueError, TypeError):
                            safe_arg = 0
                        res = inst.writeParameter(FIDX_DDE, safe_arg, verify=True, debug=True)
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
                                if idx_now == (int(arg) if arg is not None else 0) and name_now:
                                    applied = True
                                    break
                            except Exception:
                                pass
                            time.sleep(0.15)
                    if applied:
                        # optional telemetry
                        self.telemetry.emit({
                            "ts": time.time(), "port": self.port, "address": address,
                            "kind": "fluid_change", "name": "fluid_index", "value": int(arg) if arg is not None else 0
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
                        # Enhanced safe conversion for setpoint
                        try:
                            safe_arg = int(arg) if arg not in (None, "", " ") else 0
                        except (ValueError, TypeError):
                            safe_arg = 0
                        res = inst.writeParameter(SETPOINT_DDE, safe_arg)
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
                                tol = 1e-3 * max(1.0, abs(int(arg) if arg is not None else 0))
                                ok = abs((int(rb) if rb is not None else 0) - (float(arg) if arg is not None else 0.0)) <= tol
                            if not ok:
                                name = pp_status_codes.get(res, str(res))
                                self.error.emit(f"{self.port}/{address}: setpoint write timeout; verify failed (res={res} {name}, rb={rb})")
                    else:
                        # some other status → report
                        name = pp_status_codes.get(res, str(res))
                        self.error.emit(f"{self.port}/{address}: setpoint write status {res} ({name})")
                    self.telemetry.emit({
                        "ts": time.time(), "port": self.port, "address": address,
                        "kind": "setpoint", "name": "Setpoint_pct", "value": int(arg) if arg is not None else 0
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
            max_retries = 2  # Allow one retry for connection errors
            retry_count = 0
            operation_success = False
            
            while retry_count <= max_retries and not operation_success:
                try:
                    # Add small delay for shared USB devices to reduce contention
                    current_time = time.time()
                    time_since_last = current_time - self._last_operation_time
                    min_interval = 0.001  # 1ms minimum between operations on same port
                    if time_since_last < min_interval:
                        time.sleep(min_interval - time_since_last)
                    
                    # Use shared instrument with proper locking for USB device coordination
                    try:
                        inst = self.manager.get_shared_instrument(self.port, address)
                    except Exception as connection_error:
                        # Log the connection error and try once more after a delay
                        if self.manager.error_logger:
                            self.manager.error_logger.log_error(
                                self.port,
                                address,
                                "POLLER_CONNECTION_ERROR",
                                f"Connection failed for {self.port}:{address}: {connection_error}"
                            )
                        
                        # Wait a bit and try once more
                        time.sleep(1.0)
                        try:
                            inst = self.manager.get_shared_instrument(self.port, address)
                        except Exception as final_error:
                            # Final failure - emit error signal instead of crashing
                            self.error_occurred.emit(
                                f"Communication lost with device {self.port}:{address}. Error: {final_error}"
                            )
                            # Clear parameters to force re-read on next success
                            if address in self._param_cache:
                                del self._param_cache[address]
                            return  # Skip this poll cycle gracefully
                    
                    self._last_operation_time = time.time()

                    params = self._param_cache.get(address)
                    if params is None:
                        PARAMS = [FMEASURE_DDE, FNAME_DDE, MEASURE_DDE, SETPOINT_DDE, FSETPOINT_DDE, CAPACITY_DDE, IDENT_NR_DDE]
                        params = inst.db.get_parameters(PARAMS)
                        self._param_cache[address] = params
                    
                    t0 = time.perf_counter()
                    try:
                        values = inst.read_parameters(params) or []
                    except (TypeError, OSError, Exception) as read_error:
                        # Handle various connection-related errors
                        error_msg = str(read_error)
                        if "integer is required (got type NoneType)" in error_msg or "file descriptor" in error_msg or "Serial connection lost" in error_msg:
                            if self.manager.error_logger:
                                self.manager.error_logger.log_error(
                                    self.port,
                                    address,
                                    "SERIAL_CONNECTION_LOST",
                                    f"Serial file descriptor lost: {error_msg}"
                                )
                            
                            # Clear cache and emit error signal
                            if address in self._param_cache:
                                del self._param_cache[address]
                            
                            self.error_occurred.emit(
                                f"Communication lost with device {self.port}:{address}. Serial connection dropped."
                            )
                            return  # Skip this poll cycle gracefully
                        else:
                            # Re-raise non-connection errors
                            raise read_error
                    
                    operation_success = True  # If we get here, the operation succeeded
                    
                    # Process the results
                    ok, data = {}, {}
                    for p, v in zip(params, values):
                        dde = p["dde_nr"]
                        # Enhanced None and type checking
                        if v is None:
                            ok[dde] = False
                            data[dde] = None
                        else:
                            status = v.get("status") if isinstance(v, dict) else None
                            val = v.get("data") if isinstance(v, dict) else v
                            
                            ok[dde] = (status == 0 and val is not None)
                            
                            # Clean string values and handle different data types
                            if isinstance(val, str):
                                val = val.strip()
                            elif isinstance(val, bytes):
                                try:
                                    val = val.decode('utf-8', errors='ignore').strip()
                                except:
                                    val = None
                                    ok[dde] = False
                            
                            data[dde] = val
                    
                    # Continue with normal processing only if operation succeeded
                    break
                    
                except Exception as e:
                    retry_count += 1
                    error_msg = str(e).lower()
                    
                    # Check if this is a recoverable error
                    is_recoverable = any(err in error_msg for err in [
                        "bad file descriptor", "errno 9", "write failed", 
                        "device not found", "port not open"
                    ])
                    
                    if is_recoverable and retry_count <= max_retries:
                        # Clear cache and try to recover
                        try:
                            self.manager.clear_shared_instrument_cache(self.port, address)
                            if address in self._param_cache:
                                del self._param_cache[address]
                        except Exception:
                            pass
                        
                        # Wait a bit before retry
                        time.sleep(0.05)
                        continue
                    else:
                        # Not recoverable or max retries exceeded, raise the error
                        raise
            
            # Only continue with measurement processing if operation was successful
            if not operation_success:
                continue

            try:
                # after building ok/data
                name_ok = ok.get(FNAME_DDE)
                if name_ok:
                    self._last_name[address] = data[FNAME_DDE]

                f_ok = ok.get(FMEASURE_DDE)

                if f_ok:
                    # Get values for validation with proper None checking
                    fmeasure_value = data.get(FMEASURE_DDE)
                    capacity_value = data.get(CAPACITY_DDE)
                    ident_nr = data.get(IDENT_NR_DDE)
                    
                    # Validate FMEASURE against CAPACITY (skip if > 150% of capacity)
                    # Only apply validation to DMFC instruments (ident_nr == 7)
                    skip_measurement = False
                    if (ident_nr == 7 and  # Only for DMFC instruments
                        capacity_value is not None and fmeasure_value is not None):
                        try:
                            capacity_val = float(capacity_value)
                            fmeasure_val = float(fmeasure_value)
                            capacity_150_percent = capacity_val * 1.5
                            if fmeasure_val > capacity_150_percent:
                                skip_measurement = True
                                print(f"⚠️  {self.port}/{address}: DMFC validation - Skipping measurement - FMEASURE ({fmeasure_val:.3f}) exceeds 150% of capacity ({capacity_150_percent:.3f})")
                        except (ValueError, TypeError, AttributeError) as e:
                            # If conversion fails, continue with measurement
                            print(f"Warning: {self.port}/{address}: Could not validate DMFC capacity: {e}")
                            pass
                    
                    if skip_measurement:
                        # Skip this measurement cycle, don't emit measured signal
                        # Emit telemetry for the skipped measurement (DMFC only)
                        try:
                            capacity_val = float(capacity_value) if capacity_value is not None else 0.0
                            fmeasure_val = float(fmeasure_value) if fmeasure_value is not None else 0.0
                            capacity_150_percent = capacity_val * 1.5
                            
                            self.telemetry.emit({
                                "ts": time.time(), 
                                "port": self.port, 
                                "address": address,
                                "kind": "validation_skip", 
                                "name": "dmfc_capacity_exceeded", 
                                "value": fmeasure_val,
                                "capacity": capacity_val,
                                "threshold": capacity_150_percent,
                                "device_type": "DMFC",
                                "reason": f"DMFC validation: FMEASURE ({fmeasure_val:.3f}) > 150% capacity ({capacity_150_percent:.3f})"
                            })
                        except (ValueError, TypeError, AttributeError):
                            # If telemetry fails, just skip it
                            pass
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
                        fmeasure_val = data.get(FMEASURE_DDE)
                        # Enhanced safe conversion for fmeasure
                        try:
                            safe_fmeasure = float(fmeasure_val) if fmeasure_val not in (None, "", " ") else 0.0
                        except (ValueError, TypeError):
                            safe_fmeasure = 0.0
                            
                        self.measured.emit({
                            "port": self.port,
                            "address": address,
                            "data": {"fmeasure": safe_fmeasure, 
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
                        try:
                            safe_fmeasure = float(fmeasure_val) if str(fmeasure_val).strip() != "" else 0.0
                            self.telemetry.emit({
                                "ts": time.time(), "port": self.port, "address": address,
                                "kind": "measure", "name": "fMeasure", "value": safe_fmeasure
                            })
                        except (ValueError, TypeError, AttributeError):
                            # Skip telemetry if conversion fails
                            pass
            except Exception as e:
                # Enhanced error handling with specific error types and recovery mechanisms
                error_msg = str(e)
                error_type = "communication"
                should_clear_cache = False
                should_reconnect = False
                
                # Classify error types for better handling
                if "bad file descriptor" in error_msg.lower() or "errno 9" in error_msg.lower():
                    error_type = "bad_file_descriptor"
                    should_clear_cache = True
                    should_reconnect = True
                elif "port that is not open" in error_msg.lower():
                    error_type = "port_closed"
                    should_clear_cache = True
                    should_reconnect = True
                elif "device disconnected" in error_msg.lower() or "device not found" in error_msg.lower():
                    error_type = "device_disconnected"
                    should_clear_cache = True
                    should_reconnect = True
                elif "timeout" in error_msg.lower():
                    error_type = "timeout"
                elif "permission denied" in error_msg.lower() or "access denied" in error_msg.lower():
                    error_type = "permission_denied"
                    should_clear_cache = True
                elif "no such file" in error_msg.lower():
                    error_type = "device_not_found"
                    should_clear_cache = True
                elif "write failed" in error_msg.lower():
                    error_type = "write_failed"
                    should_clear_cache = True
                    should_reconnect = True
                
                # Recovery actions
                if should_clear_cache:
                    try:
                        # Clear the shared instrument cache for this address to force reconnection
                        self.manager.clear_shared_instrument_cache(self.port, address)
                        # Also clear parameter cache to force fresh parameter lookup
                        if address in self._param_cache:
                            del self._param_cache[address]
                    except Exception:
                        pass
                
                if should_reconnect and hasattr(self.manager, 'force_reconnect_port'):
                    try:
                        # Schedule a port reconnection attempt
                        self.manager.force_reconnect_port(self.port)
                    except Exception:
                        pass
                
                self.error.emit(f"Poll error on {self.port}/{address}: {e} (type: {error_type})")
                
                # For critical errors, add a small delay before continuing
                if error_type in ["bad_file_descriptor", "port_closed", "device_disconnected", "write_failed"]:
                    time.sleep(0.1)

            # remember who we just serviced
            self._last_addr = address

            # 4) Reschedule drift-free (unchanged)
            next_due = due + period
            while next_due <= time.monotonic():
                next_due += period
            heapq.heappush(self._heap, (next_due, address, period))
