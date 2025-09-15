# backend/poller.py
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import time, heapq, queue

class PortPoller(QObject):
    measured = pyqtSignal(object)   # emits {"port", "address", "data": {"fmeasure", "name"}, "ts"}
    error    = pyqtSignal(str)

    def __init__(self, manager, port, default_period=0.5):
        super().__init__()
        self.manager = manager
        self.port = port
        self.default_period = float(default_period)
        self._running = True
        self._heap = []                 # (next_due, address, period)
        self._known = {}                # address -> (period)
        self._cmd_q = queue.Queue()     # serialize writes/one-off reads

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
        while self._running:
            now = time.monotonic()

            # 1) Execute at most one queued command (keeps latency low)
            try:
                kind, address, arg = self._cmd_q.get_nowait()
                inst = inst_cache.get(address)
                if inst is None:
                    inst = self.manager.instrument(self.port, address)
                    inst_cache[address] = inst
                if kind == "fluid":
                    ok = inst.writeParameter(24, arg)
                    if not ok:
                        self.error.emit(f"Port {self.port} addr {address}: failed to set fluid index {arg}")
                # you can add more command kinds here
            except queue.Empty:
                pass
            except Exception as e:
                self.error.emit(str(e))

            # 2) Poll the next due instrument
            if self._heap:
                due, address, period = self._heap[0]
                sleep_for = max(0.0, due - now)
            else:
                sleep_for = 0.1

            if sleep_for > 0:
                time.sleep(min(sleep_for, 0.05))
                continue

            heapq.heappop(self._heap)
            # address might have been removed; skip if no longer known
            if address not in self._known:
                continue

            # do one read cycle
            try:
                inst = inst_cache.get(address)
                if inst is None:
                    inst = self.manager.instrument(self.port, address)
                    inst_cache[address] = inst

                ddes   = [205, 25]  # fMeasure + Fluid name
                params = inst.db.get_parameters(ddes)
                values = inst.read_parameters(params) or []

                ok = {}
                data = {}
                for p, v in zip(params, values):
                    dde = p["dde_nr"]
                    ok[dde] = (v.get("status") == 0 and v.get("data") is not None)
                    val = v.get("data")
                    if isinstance(val, str):
                        val = val.strip()
                    data[dde] = val

                if ok.get(205) and ok.get(25):
                    payload = {
                        "port": self.port,
                        "address": address,
                        "data": {"fmeasure": float(data[205]), "name": data[25]},
                        "ts": time.time(),
                    }
                    self.measured.emit(payload)

            except Exception as e:
                # swallow individual read errors; keep the cadence
                self.error.emit(f"Poll error on {self.port}/{address}: {e}")

            # reschedule with drift-free cadence
            next_due = due + period
            # if we fell behind, catch up without piling many immediate polls
            while next_due <= time.monotonic() - 0.001:
                next_due += period
            heapq.heappush(self._heap, (next_due, address, period))
