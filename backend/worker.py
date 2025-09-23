from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, QTimer
import csv, os, time, queue
from statistics import mean

class TelemetryLogWorker(QObject):
    error = pyqtSignal(str)
    started = pyqtSignal(str)
    stopped = pyqtSignal(str)

    def __init__(self, path, *, filter_port=None, filter_address=None, interval_min=1, usertag=None, parent=None):
        super().__init__(parent)
        self._path = path
        self._filter_port = filter_port
        self._filter_address = filter_address
        self._interval = interval_min * 60  # convert minutes to seconds
        self._running = False
        self._usertag = usertag
        self._q = queue.Queue()
        self._fh = None
        self._count_since_flush = 0
        self._fmeasure_buffer = []
        self._last_avg_time = time.time()


    @pyqtSlot()
    def run(self):
        try:
            is_new = not os.path.exists(self._path)
            self._fh = open(self._path, "a", newline="")
            self._writer = csv.writer(self._fh)
            if is_new:
                self._writer.writerow(["ts","iso","port","address","kind","name","value","unit","extra", "usertag"])
            self._running = True
            self.started.emit(self._path)
        except Exception as e:
            self.error.emit(f"Open log failed: {e}")
            return

        # start periodic processing via QTimer
        self._timer = QTimer()
        self._timer.setInterval(200)  # adjust as needed
        self._timer.timeout.connect(self._process_queue)
        self._timer.start()

    
    def _process_queue(self):
        if not self._running:
            return
        
        now = time.time()

        try:
            while not self._q.empty():
                rec = self._q.get_nowait()
                val = rec.get("value", None)
                if isinstance(val, (int, float)):
                    self._fmeasure_buffer.append(val)
        except queue.Empty:
            pass

        if now - self._last_avg_time >= self._interval and self._fmeasure_buffer:
            self._write_average(now)

    def _write_average(self, ts=None):
        if not self._fmeasure_buffer:
            return

        ts = ts or time.time()
        iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        avg_val = mean(self._fmeasure_buffer)

        row = [
            f"{ts:.3f}",
            iso,
            self._filter_port or "",
            self._filter_address or "",
            "measure",
            "fMeasure",
            f"{avg_val:.5f}",
            "",
            f"{len(self._fmeasure_buffer)} samples",
            self._usertag or ""
        ]

        try:
            self._writer.writerow(row)
            self._fh.flush()
        except Exception as e:
            self.error.emit(f"Averaged write failed: {e}")

        self._fmeasure_buffer.clear()
        self._last_avg_time = ts

    @pyqtSlot(object)
    def on_record(self, rec):
        # called via Qt signal (QueuedConnection) from main thread
        # Filter based on port and/or address if set
        if self._filter_port and rec.get("port") != self._filter_port:
            return
        if self._filter_address and rec.get("address") != self._filter_address:
            return

        kind = rec.get("kind")
        if kind == "measure":
            try:
                self._q.put_nowait(rec)
            except queue.Full:
                # drop oldest to keep up
                try:
                    _ = self._q.get_nowait()
                except Exception:
                    pass
                try:
                    self._q.put_nowait(rec)
                except Exception:
                    self.error.emit("Log queue full; record dropped.")
        else:
            self._write_event_row(rec)

    
    def _write_event_row(self, rec):
        try:
            ts = rec.get("ts", time.time())
            iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
            row = [
                f"{ts:.3f}",
                iso,
                rec.get("port", ""),
                rec.get("address", ""),
                rec.get("kind", ""),     # e.g. "setpoint"
                rec.get("name", ""),     # e.g. "fSetpoint"
                rec.get("value", ""),
                rec.get("unit", ""),
                rec.get("extra", ""),
                self._usertag or ""
            ]
            self._writer.writerow(row)
            self._fh.flush()
        except Exception as e:
            self.error.emit(f"Immediate write failed: {e}")
    

    def stop(self):
        self._running = False
        if hasattr(self, "_timer"):
            self._timer.stop()
        try:
            if self._fh:
                self._fh.flush()
                self._fh.close()
        except Exception:
            pass
        self.stopped.emit(self._path)


