# backend/poller.py
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import time, heapq, queue
from propar_new import PP_STATUS_OK, PP_STATUS_TIMEOUT_ANSWER, pp_status_codes

FSETPOINT_DDE = 206  # fSetpoint
FIDX_DDE = 24      # fluid index
FNAME_DDE = 25     # fluid name
IGNORE_TIMEOUT_ON_SETPOINT = False


class PortPoller(QObject):
    measured = pyqtSignal(object)   # emits {"port", "address", "data": {"fmeasure", "name"}, "ts"}
    error    = pyqtSignal(str)

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
        self._param_cache = {}    # NEW: address -> [param dicts]  ← avoid get_parameters() every time
        self._cmd_q = queue.Queue()     # serialize writes/one-off reads
    
    def request_setpoint_flow(self, address: int, flow_value: float):
        """Queue a write of fSetpoint (engineering units) for this instrument."""
        self._cmd_q.put(("fset_flow", int(address), float(flow_value)))

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
        inst_cache = {}
        FAIR_WINDOW = 0.005  # 5 ms window to consider multiple items "simultaneously due"

        while self._running:
            now = time.monotonic()

            # 1) (unchanged) handle 1 queued command...
            try:
                kind, address, arg = self._cmd_q.get_nowait()
                inst = inst_cache.get(address)
                if inst is None:
                    inst = self.manager.instrument(self.port, address)
                    inst_cache[address] = inst
                    # NEW: tighten timeouts for polling
                    inst.master.response_timeout = 0.08     # default is 0.5 s, too slow for polling
                    inst.master.propar.serial.timeout = 0.005
                
                elif kind == "fluid":
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
                    applied = False
                    if ok_immediate:
                        applied = True  # we'll still verify below to be sure
                    elif isinstance(res, int) and res == PP_STATUS_TIMEOUT_ANSWER:
                        # expected sometimes; proceed to verify
                        pass
                    else:
                        # unknown shape → verify anyway
                        pass

                    # Verify loop: wait until device reports the new index & a non-empty name
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

                    if not ok_immediate and res == PP_STATUS_TIMEOUT_ANSWER:
                        time.sleep(0.2)
                        res = inst.writeParameter(FIDX_DDE, int(arg))

                    if not applied:
                        self.error.emit(f"{self.port}/{address}: fluid change to {arg} timed out (res={res})")
                                
                #elif kind == "fset_flow":
                #    ok = inst.writeParameter(FSETPOINT_DDE, float(arg), verify=True, debug=True)
                ##    print(ok)
                 #   if not ok:
                 #       self.error.emit(f"Port {self.port} addr {address}: failed to set fSetpoint {arg}")
                # inside PortPoller.run(), in the command block
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

            except queue.Empty:
                pass
            except Exception as e:
                self.error.emit(str(e))

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

            # 3) Do one read cycle (unchanged)
            try:
                inst = inst_cache.get(address)
                if inst is None:
                    inst = self.manager.instrument(self.port, address)
                    inst_cache[address] = inst
                     # NEW: tighten timeouts at creation
                    inst.master.response_timeout = 0.08
                    inst.master.propar.serial.timeout = 0.005

                params = self._param_cache.get(address)
                if params is None:
                    params = inst.db.get_parameters([205, 25])
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

                if ok.get(205) and ok.get(25):
                    self.measured.emit({
                        "port": self.port,
                        "address": address,
                        "data": {"fmeasure": float(data[205]), "name": data[25]},
                        "ts": time.time(),
                    })

            except Exception as e:
                self.error.emit(f"Poll error on {self.port}/{address}: {e}")

            # remember who we just serviced
            self._last_addr = address

            # 4) Reschedule drift-free (unchanged)
            next_due = due + period
            while next_due <= time.monotonic():
                next_due += period
            heapq.heappush(self._heap, (next_due, address, period))
