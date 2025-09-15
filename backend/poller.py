# backend/poller.py
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import time, heapq, queue

FSETPOINT_DDE = 206  # fSetpoint

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
                if kind == "fluid":
                    ok = inst.writeParameter(24, arg, verify=True, debug=True)
                    if not ok:
                        self.error.emit(f"Port {self.port} addr {address}: failed to set fluid index {arg}")
                if kind == "fset_flow":
                    ok = inst.writeParameter(FSETPOINT_DDE, float(arg), verify=True, debug=True)
                    print(ok)
                    if not ok:
                        self.error.emit(f"Port {self.port} addr {address}: failed to set fSetpoint {arg}")

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
