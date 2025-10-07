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

    def __init__(self, manager, port, addresses=None, default_period=0.5):
        """
        Initialize PortPoller with flexible address support.
        
        Args:
            manager: Manager instance
            port (str): Serial port (e.g., '/dev/ttyUSB0')
            addresses (int|list|None): Single address, list of addresses, or None for backward compatibility
            default_period (float): Default polling period in seconds
        """
        super().__init__()
        self.manager = manager
        self.port = port
        self.default_period = float(default_period)
        self._running = True
        self._last_addr = None
        self._heap = []                 # (next_due, address, period)
        self._known = {}                # address -> (period)
        self._cmd_q = queue.Queue()     # serialize writes/one-off reads
        self._param_cache = {}          # address -> [param dicts]  ← avoid get_parameters() every time
        self._last_name = {}
        
        # Flexible address handling with validation
        if addresses is None:
            self.addresses = []  # Will be populated via add_node()
        elif isinstance(addresses, int):
            if 1 <= addresses <= 247:
                self.addresses = [addresses]  # Single address mode (backward compatibility)
            else:
                print(f"PortPoller: Invalid address {addresses} for {self.port}, must be 1-247")
                self.addresses = []
        elif isinstance(addresses, (list, tuple)):
            # Validate all addresses in the list
            valid_addresses = []
            for addr in addresses:
                try:
                    addr_int = int(addr)
                    if 1 <= addr_int <= 247:
                        valid_addresses.append(addr_int)
                    else:
                        print(f"PortPoller: Invalid address {addr} for {self.port}, must be 1-247")
                except (ValueError, TypeError):
                    print(f"PortPoller: Invalid address format '{addr}' for {self.port}, must be integer")
            self.addresses = valid_addresses  # Multi-address mode
        else:
            self.addresses = []
        
        # Multi-address polling coordination
        self._address_index = 0  # Round-robin index for fair polling
        self._address_fairness = {}  # Track polling fairness per address
        
        # Add small delay for shared USB devices to reduce contention
        self._last_operation_time = 0
        
        # Error tracking for consecutive failures
        self._consecutive_errors = {}  # address -> error_count
        self._last_error_time = {}     # address -> timestamp
        
        # Connection stability tracking
        self._connection_recoveries = {}  # address -> recovery_count
        self._last_recovery_time = {}     # address -> timestamp
        self._connection_uptime = {}      # address -> last_successful_time
        
        print(f"PortPoller initialized for {self.port} with addresses: {self.addresses}")
        
        # Auto-add pre-configured addresses
        if self.addresses:
            for addr in self.addresses:
                self.add_node(addr)            

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
        """Add a node for polling. Works with both pre-configured and dynamic addresses."""
        # Validate and normalize address
        try:
            address = int(address)
            if not (1 <= address <= 247):  # Valid ProPar address range
                print(f"PortPoller: Invalid address {address} for {self.port}, must be 1-247")
                return
        except (ValueError, TypeError):
            print(f"PortPoller: Invalid address format '{address}' for {self.port}, must be integer")
            return
            
        period = float(period or self.default_period)
        if address in self._known:
            return
        
        # Add to known addresses
        self._known[address] = period
        
        # Add to addresses list if not already present (for dynamic addition)
        if address not in self.addresses:
            self.addresses.append(address)
            print(f"Node {address} dynamically added to {self.port} poller")
        
        # small staggering based on current count to avoid bursts
        t0 = time.monotonic() + (len(self._known) * 0.02)
        heapq.heappush(self._heap, (t0, address, period))
        
        # Initialize fairness tracking
        self._address_fairness[address] = 0
        
        print(f"Node {address} added to {self.port} poller (total: {len(self.addresses)} addresses)")
    
    def _validate_address(self, address):
        """Validate and normalize address to ensure it's a proper integer."""
        try:
            addr_int = int(address)
            if 1 <= addr_int <= 247:
                return addr_int
            else:
                print(f"PortPoller: Address {address} out of valid range (1-247) for {self.port}")
                return None
        except (ValueError, TypeError):
            print(f"PortPoller: Invalid address format '{address}' for {self.port}")
            return None

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
        print(f"PortPoller started for {self.port}")

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
                    # Get device identification to check if gas compensation should be applied
                    device_type = None
                    gas_factor = 1.0
                    device_setpoint = float(arg)  # Send user value directly to device (no compensation on setpoint)
                    
                    # Check if this is a DMFC device for telemetry logging
                    if hasattr(self, 'manager') and self.manager:
                        try:
                            # Get device type from manager's node cache
                            device_type = self.manager.get_device_type(self.port, address)
                            
                            # Get gas factor for telemetry purposes only (not for setpoint compensation)
                            if device_type == "DMFC":
                                serial_nr = self.manager.get_serial_number(self.port, address)
                                gas_factor = self.manager.get_gas_factor(self.port, address, serial_nr)
                                # NOTE: We do NOT compensate the setpoint - device handles this internally
                        except Exception:
                            # If anything fails, use original value
                            pass
                    
                    # slightly higher timeout for writes (still much lower than 0.5s default)
                    old_rt = getattr(inst.master, "response_timeout", 0.5)
                    try:
                        inst.master.response_timeout = max(old_rt, 0.20)
                        res = inst.writeParameter(FSETPOINT_DDE, device_setpoint)
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
                                tol = 1e-3 * max(1.0, abs(float(device_setpoint)))
                                ok = abs(float(rb) - float(device_setpoint)) <= tol
                            if not ok:
                                name = pp_status_codes.get(res, str(res))
                                self.error.emit(f"{self.port}/{address}: setpoint write timeout; verify failed (res={res} {name}, rb={rb})")
                    else:
                        # some other status → report
                        name = pp_status_codes.get(res, str(res))
                        self.error.emit(f"{self.port}/{address}: setpoint write status {res} ({name})")
                    # Emit setpoint telemetry
                    if device_type == "DMFC" and gas_factor != 1.0:
                        # For DMFC devices: emit both the compensated and raw setpoint values
                        # Compensated setpoint (what the gas actually achieves) - main telemetry
                        compensated_setpoint = device_setpoint * gas_factor if gas_factor != 0 else device_setpoint
                        self.telemetry.emit({
                            "ts": time.time(), "port": self.port, "address": address,
                            "kind": "setpoint", "name": "fSetpoint", "value": round(compensated_setpoint, 1)
                        })
                        # Raw device setpoint (what we actually send to device) - raw telemetry
                        self.telemetry.emit({
                            "ts": time.time(), "port": self.port, "address": address,
                            "kind": "setpoint", "name": "fSetpoint_raw", "value": round(device_setpoint, 1)
                        })
                    else:
                        # Non-DMFC or no compensation: emit normal setpoint
                        self.telemetry.emit({
                            "ts": time.time(), "port": self.port, "address": address,
                            "kind": "setpoint", "name": "fSetpoint", "value": round(float(arg), 1)
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

            # Validate address format - ensure it's a proper integer
            try:
                address = int(address)
                if not (1 <= address <= 247):  # Valid ProPar address range
                    print(f"PortPoller: Invalid address {address} on {self.port}, skipping")
                    continue
            except (ValueError, TypeError):
                print(f"PortPoller: Invalid address format '{address}' on {self.port}, skipping")
                continue

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
                                f"Communication lost with device {self.port} address {address}. Error: {final_error}"
                            )
                            # Clear parameters to force re-read on next success
                            if address in self._param_cache:
                                del self._param_cache[address]
                            # Reschedule node for next poll cycle before returning
                            next_due = due + period
                            while next_due <= time.monotonic():
                                next_due += period
                            heapq.heappush(self._heap, (next_due, address, period))
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
                        if ("integer is required (got type NoneType)" in error_msg or 
                            "file descriptor" in error_msg or 
                            "Serial connection lost" in error_msg or
                            "port is closed" in error_msg or
                            "file descriptor is None" in error_msg):
                            
                            # Track consecutive errors for this specific error type
                            current_time = time.time()
                            if address not in self._consecutive_errors:
                                self._consecutive_errors[address] = 0
                                
                            # Reset error count if enough time has passed since last error
                            if address in self._last_error_time:
                                if current_time - self._last_error_time[address] > 30:  # Reset after 30 seconds
                                    self._consecutive_errors[address] = 0
                                    
                            self._consecutive_errors[address] += 1
                            self._last_error_time[address] = current_time
                            
                            # Log the error with enhanced context
                            if self.manager.error_logger:
                                self.manager.error_logger.log_error(
                                    self.port,
                                    address,
                                    "SERIAL_CONNECTION_LOST",
                                    f"Serial file descriptor lost: {error_msg}",
                                    error_details=f"Consecutive errors: {self._consecutive_errors[address]}, Port: {self.port}, Address: {address}"
                                )
                            
                            # Enhanced recovery actions
                            try:
                                # Clear the shared instrument cache for this address
                                self.manager.clear_shared_instrument_cache(self.port, address)
                                # Also clear parameter cache to force fresh parameter lookup
                                if address in self._param_cache:
                                    del self._param_cache[address]
                                print(f"Cleared cache for {self.port} address {address} due to serial connection lost")
                            except Exception as cache_error:
                                print(f"Error clearing cache: {cache_error}")
                            
                            # Force port reconnection for this specific error
                            if hasattr(self.manager, 'force_reconnect_port'):
                                try:
                                    print(f"Attempting reconnection for {self.port} due to serial connection lost")
                                    self.manager.force_reconnect_port(self.port)
                                except Exception as reconnect_error:
                                    print(f"Reconnection failed for {self.port}: {reconnect_error}")
                            
                            # If too many consecutive errors, temporarily disable this address
                            if self._consecutive_errors[address] >= 10:
                                print(f"Too many consecutive serial errors ({self._consecutive_errors[address]}) for {self.port} address {address}, temporarily disabling")
                                # Remove from known addresses temporarily
                                self._known.pop(address, None)
                                # Re-add after a longer delay
                                def re_enable_address():
                                    time.sleep(60)  # Wait 1 minute
                                    if address in self.addresses:  # Only if it's in our configured addresses
                                        self.add_node(address)
                                        self._consecutive_errors[address] = 0
                                        print(f"Re-enabled {self.port} address {address} after serial error recovery")
                                
                                # Start re-enable in background
                                import threading
                                threading.Thread(target=re_enable_address, daemon=True).start()
                                return  # Skip further processing for this cycle
                            
                            # Clear cache and emit error signal
                            self.error_occurred.emit(
                                f"Communication lost with device {self.port} address {address}. Serial connection dropped."
                            )
                            
                            # Reschedule node for next poll cycle with longer delay for serial errors
                            next_due = due + period + 1.0  # Add 1 second extra delay for serial errors
                            while next_due <= time.monotonic():
                                next_due += period
                            heapq.heappush(self._heap, (next_due, address, period))
                            return  # Skip this poll cycle gracefully
                        else:
                            # Re-raise non-connection errors
                            raise read_error
                    
                    operation_success = True  # If we get here, the operation succeeded
                    
                    # Reset error count on successful communication
                    if address in self._consecutive_errors and self._consecutive_errors[address] > 0:
                        # Track connection recovery
                        current_time = time.time()
                        if address not in self._connection_recoveries:
                            self._connection_recoveries[address] = 0
                        self._connection_recoveries[address] += 1
                        self._last_recovery_time[address] = current_time
                        
                        # Calculate downtime if we have previous error time
                        downtime = 0
                        if address in self._last_error_time:
                            downtime = current_time - self._last_error_time[address]
                        
                        print(f"Communication restored for {self.port} address {address}, resetting error count")
                        print(f"  Recovery #{self._connection_recoveries[address]}, downtime: {downtime:.1f}s")
                        
                        # Log recovery event
                        if hasattr(self.manager, 'error_logger') and self.manager.error_logger:
                            self.manager.error_logger.log_error(
                                self.port,
                                address,
                                "CONNECTION_RECOVERY",
                                f"Communication restored after {downtime:.1f}s downtime",
                                error_details=f"Recovery #{self._connection_recoveries[address]}, Consecutive errors cleared: {self._consecutive_errors[address]}"
                            )
                        
                        self._consecutive_errors[address] = 0
                        
                        # Print connection summary after recovery
                        print("\n📊 CONNECTION RECOVERY SUMMARY:")
                        self.print_connection_summary()
                    
                    # Update connection uptime tracking
                    self._connection_uptime[address] = time.time()
                    
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
                            safe_fmeasure_raw = float(fmeasure_val) if fmeasure_val not in (None, "", " ") else 0.0
                        except (ValueError, TypeError):
                            safe_fmeasure_raw = 0.0

                        # Apply gas compensation factor (only for DMFC devices, ident_nr == 7)
                        if hasattr(self, 'manager') and self.manager and ident_nr == 7:
                            # Get serial number for persistent gas factor lookup
                            serial_nr = self.manager.get_serial_number(self.port, address)
                            gas_factor = self.manager.get_gas_factor(self.port, address, serial_nr)
                            safe_fmeasure = safe_fmeasure_raw * gas_factor
                            
                            # Emit raw telemetry if gas factor is applied (not 1.0)
                            if gas_factor != 1.0:
                                self.telemetry.emit({
                                    "ts": time.time(), "port": self.port, "address": address,
                                    "kind": "measure", "name": "fMeasure_raw", "value": safe_fmeasure_raw
                                })
                        else:
                            # No gas compensation for non-DMFC devices
                            safe_fmeasure = safe_fmeasure_raw
                            
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
                            safe_fmeasure_raw = float(fmeasure_val) if str(fmeasure_val).strip() != "" else 0.0
                            
                            # Apply gas compensation factor for telemetry (only for DMFC devices, ident_nr == 7)
                            if hasattr(self, 'manager') and self.manager and ident_nr == 7:
                                # Get serial number for persistent gas factor lookup
                                serial_nr = self.manager.get_serial_number(self.port, address)
                                gas_factor = self.manager.get_gas_factor(self.port, address, serial_nr)
                                safe_fmeasure = safe_fmeasure_raw * gas_factor
                            else:
                                safe_fmeasure = safe_fmeasure_raw
                            
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
                
                # Enhanced error classification for better USB disconnection handling
                error_msg_lower = error_msg.lower()
                
                # USB disconnection indicators
                usb_disconnect_indicators = [
                    "bad file descriptor", "errno 9", "write failed", "read failed",
                    "device disconnected", "device not found", "no such file or directory",
                    "port that is not open", "serial exception", "connection lost",
                    "file descriptor is none", "port is closed", "serial connection lost"
                ]
                
                if any(indicator in error_msg_lower for indicator in usb_disconnect_indicators):
                    if "bad file descriptor" in error_msg_lower or "errno 9" in error_msg_lower:
                        error_type = "bad_file_descriptor"
                    elif "write failed" in error_msg_lower or "read failed" in error_msg_lower:
                        error_type = "write_read_failed"
                    elif "device disconnected" in error_msg_lower or "device not found" in error_msg_lower:
                        error_type = "device_disconnected"
                    elif "no such file" in error_msg_lower:
                        error_type = "device_not_found"
                    elif ("port that is not open" in error_msg_lower or 
                          "port is closed" in error_msg_lower or
                          "file descriptor is none" in error_msg_lower):
                        error_type = "port_closed"
                    elif "serial connection lost" in error_msg_lower or "connection lost" in error_msg_lower:
                        error_type = "serial_connection_lost"
                    else:
                        error_type = "usb_disconnection"
                    
                    should_clear_cache = True
                    should_reconnect = True
                    
                    # Log USB disconnection event
                    if hasattr(self.manager, 'error_logger') and self.manager.error_logger:
                        self.manager.error_logger.log_error(
                            port=self.port,
                            address=str(address),
                            error_type="SERIAL_CONNECTION_LOST",
                            error_message=f"Serial file descriptor lost: {error_msg}",
                            error_details=f"Error type: {error_type}, Port: {self.port}, Address: {address}"
                        )
                        
                elif "timeout" in error_msg_lower:
                    error_type = "timeout"
                elif "permission denied" in error_msg_lower or "access denied" in error_msg_lower:
                    error_type = "permission_denied"
                    should_clear_cache = True
                else:
                    error_type = "communication"
                
                # Enhanced recovery actions for USB disconnections
                if should_clear_cache:
                    try:
                        # Clear the shared instrument cache for this address to force reconnection
                        self.manager.clear_shared_instrument_cache(self.port, address)
                        # Also clear parameter cache to force fresh parameter lookup
                        if address in self._param_cache:
                            del self._param_cache[address]
                        print(f"Cleared cache for {self.port} address {address} due to {error_type}")
                    except Exception as cache_error:
                        print(f"Error clearing cache: {cache_error}")
                
                # Track consecutive errors for this address
                current_time = time.time()
                if address not in self._consecutive_errors:
                    self._consecutive_errors[address] = 0
                    
                # Reset error count if enough time has passed since last error
                if address in self._last_error_time:
                    if current_time - self._last_error_time[address] > 30:  # Reset after 30 seconds
                        self._consecutive_errors[address] = 0
                        
                self._consecutive_errors[address] += 1
                self._last_error_time[address] = current_time
                
                # Print summary every 3 errors for monitoring
                if self._consecutive_errors[address] % 3 == 0 and self._consecutive_errors[address] < 10:
                    print(f"\n📈 ERROR PATTERN UPDATE ({self._consecutive_errors[address]} consecutive):")
                    self.print_connection_summary()
                
                # If too many consecutive errors, temporarily disable this address
                if self._consecutive_errors[address] >= 10:
                    print(f"Too many consecutive errors ({self._consecutive_errors[address]}) for {self.port} address {address}, temporarily disabling")
                    print("\n⚠️  HIGH ERROR COUNT - CONNECTION SUMMARY:")
                    self.print_connection_summary()
                    # Remove from known addresses temporarily
                    self._known.pop(address, None)
                    # Re-add after a longer delay
                    def re_enable_address():
                        time.sleep(60)  # Wait 1 minute
                        if address in self.addresses:  # Only if it's in our configured addresses
                            self.add_node(address)
                            self._consecutive_errors[address] = 0
                            print(f"Re-enabled {self.port} address {address} after error recovery")
                    
                    # Start re-enable in background (simplified for this context)
                    import threading
                    threading.Thread(target=re_enable_address, daemon=True).start()
                    return  # Skip further processing for this cycle
                
                # Immediate reconnection for critical USB errors
                if should_reconnect and hasattr(self.manager, 'force_reconnect_port'):
                    try:
                        print(f"Attempting reconnection for {self.port} due to {error_type}")
                        self.manager.force_reconnect_port(self.port)
                    except Exception as reconnect_error:
                        print(f"Reconnection failed for {self.port}: {reconnect_error}")
                        
                # For USB disconnections, also emit specific error signal
                if error_type in ["bad_file_descriptor", "write_read_failed", "device_disconnected", "usb_disconnection", "serial_connection_lost", "port_closed"]:
                    self.error_occurred.emit(
                        f"Communication lost with device {self.port} address {address}. Serial connection dropped."
                    )
                
                # Emit error with enhanced context
                self.error.emit(f"Poll error on {self.port} address {address}: {e} (type: {error_type})")
                
                # Variable delay based on error severity
                if error_type in ["bad_file_descriptor", "write_read_failed", "device_disconnected", "usb_disconnection", "serial_connection_lost"]:
                    # Longer delay for USB disconnections to allow device recovery
                    time.sleep(1.0)
                    print(f"USB error recovery delay for {self.port} address {address}")
                elif error_type in ["port_closed", "device_not_found"]:
                    # Medium delay for port issues
                    time.sleep(0.5)
                elif error_type == "timeout":
                    # Short delay for timeouts
                    time.sleep(0.1)
                else:
                    # Minimal delay for other communication errors
                    time.sleep(0.05)

            # remember who we just serviced
            self._last_addr = address

            # 4) Reschedule drift-free (unchanged)
            next_due = due + period
            while next_due <= time.monotonic():
                next_due += period
            heapq.heappush(self._heap, (next_due, address, period))

    def get_connection_stats(self):
        """Return connection stability statistics."""
        current_time = time.monotonic()
        
        # Calculate uptime as time since oldest successful connection
        uptime = 0
        if self._connection_uptime:
            oldest_connection = min(self._connection_uptime.values())
            uptime = current_time - oldest_connection
        
        # Sum recoveries across all addresses
        total_recoveries = sum(self._connection_recoveries.values()) if self._connection_recoveries else 0
        total_consecutive_errors = sum(self._consecutive_errors.values()) if self._consecutive_errors else 0
        
        # Get most recent recovery time across all addresses
        most_recent_recovery = None
        if self._last_recovery_time:
            most_recent_recovery = max(self._last_recovery_time.values())
        
        # Get most recent error time across all addresses  
        most_recent_error = None
        if self._last_error_time:
            most_recent_error = max(self._last_error_time.values())
        
        return {
            'port': self.port,
            'connection_recoveries': total_recoveries,
            'connection_recoveries_by_address': dict(self._connection_recoveries),
            'last_recovery_time': most_recent_recovery,
            'uptime_seconds': uptime,
            'consecutive_errors': total_consecutive_errors,
            'consecutive_errors_by_address': dict(self._consecutive_errors),
            'last_error_time': most_recent_error
        }
    
    def print_connection_summary(self):
        """Print a summary of connection stability."""
        stats = self.get_connection_stats()
        print(f"\n=== Connection Summary for {stats['port']} ===")
        print(f"Total recoveries: {stats['connection_recoveries']}")
        if stats['connection_recoveries_by_address']:
            print(f"Recoveries by address: {stats['connection_recoveries_by_address']}")
        if stats['last_recovery_time']:
            print(f"Last recovery: {time.strftime('%H:%M:%S', time.localtime(stats['last_recovery_time']))}")
        print(f"Uptime: {stats['uptime_seconds']:.1f} seconds")
        print(f"Current consecutive errors: {stats['consecutive_errors']}")
        if stats['consecutive_errors_by_address']:
            print(f"Errors by address: {stats['consecutive_errors_by_address']}")
        if stats['last_error_time']:
            print(f"Last error: {time.strftime('%H:%M:%S', time.localtime(stats['last_error_time']))}")
        print("=" * 40)
