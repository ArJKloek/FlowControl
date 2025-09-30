from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, QTimer
import os, time, queue, csv
from statistics import mean
from collections import deque
class TelemetryLogWorker(QObject):
    """Adaptive telemetry logger with two modes:

    Baseline mode: aggregate measurements and write an average every `interval_min` minutes.
    Fast mode: when a significant change between successive samples is detected, write individual
    samples at `fast_interval_sec` until the signal stabilizes (no significant changes for
    `sustain_seconds` and at least `min_fast_seconds` elapsed).
    """

    error = pyqtSignal(str)
    started = pyqtSignal(str)
    stopped = pyqtSignal(str)
    request_stop = pyqtSignal()

    def __init__(self, path=None, *, filter_port=None, filter_address=None, interval_min, usertag=None,
                 parent=None, fast_interval_sec: float = 1.0, change_threshold_abs: float = 1.0,
                 change_threshold_pct: float = 0.05, sustain_seconds: float = 5.0,
                 min_fast_seconds: float = 3.0, window_sec: float = 10.0):
        super().__init__(parent)
        self._usertag = usertag
        data_dir = os.path.join(os.getcwd(), "Data")
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.join(data_dir, f"log_{self._usertag}.csv" if self._usertag else "log_unknown.csv")
        self._filter_port = filter_port
        self._filter_address = filter_address
        self._interval = interval_min * 60.0
        self._running = False
        self._q = queue.Queue()
        self._fh = None
        self._fmeasure_buffer = []
        self._last_avg_time = time.time()
        self.request_stop.connect(self.stop)
        # adaptive config
        self._fast_interval = float(fast_interval_sec)
        self._change_thresh_abs = float(change_threshold_abs)
        self._change_thresh_pct = float(change_threshold_pct)
        self._sustain_seconds = float(sustain_seconds)
        self._min_fast_seconds = float(min_fast_seconds)
        self._window_sec = float(window_sec)
        # state
        self._recent_values = deque()  # (ts,value)
        self._fast_mode = False
        self._fast_mode_since = 0.0
        self._last_fast_emit = 0.0
        self._last_value = None
        self._stable_since = time.time()

    @pyqtSlot()
    def run(self):
        try:
            is_new = not os.path.exists(self._path)
            self._fh = open(self._path, "a", newline="")
            self._writer = csv.writer(self._fh)
            if is_new:
                self._writer.writerow(["ts","iso","port","address","kind","name","value","unit","extra","usertag"])
            self._running = True
            self.started.emit(self._path)
        except Exception as e:
            self.error.emit(f"Open log failed: {e}")
            return

        self._timer = QTimer()
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._process_queue)
        self._timer.start()

    def _process_queue(self):
        if not self._running:
            return
        now = time.time()
        try:
            while not self._q.empty():
                rec = self._q.get_nowait()
                val = rec.get("value")
                if isinstance(val, (int, float)):
                    self._ingest_value(now, float(val))
        except queue.Empty:
            pass

        if self._fast_mode:
            if (now - self._last_fast_emit) >= self._fast_interval and self._last_value is not None:
                self._emit_fast(now, self._last_value)
            if (now - self._fast_mode_since) >= self._min_fast_seconds and (now - self._stable_since) >= self._sustain_seconds:
                self._fast_mode = False
        else:
            if (now - self._last_avg_time) >= self._interval and self._fmeasure_buffer:
                self._write_average(now)

    def _ingest_value(self, now: float, v: float):
        self._fmeasure_buffer.append(v)
        self._last_value = v
        self._recent_values.append((now, v))
        cutoff = now - self._window_sec
        while self._recent_values and self._recent_values[0][0] < cutoff:
            self._recent_values.popleft()
        if len(self._recent_values) >= 2:
            prev = self._recent_values[-2][1]
            delta = abs(v - prev)
            pct = delta / max(1e-9, abs(prev))
            significant = (delta >= self._change_thresh_abs) or (pct >= self._change_thresh_pct)
            if significant:
                self._stable_since = now
                if not self._fast_mode:
                    self._fast_mode = True
                    self._fast_mode_since = now
                    self._last_fast_emit = 0.0
            else:
                if not self._fast_mode:
                    self._stable_since = min(self._stable_since, now) if self._stable_since else now

    def _emit_fast(self, ts: float, value: float):
        iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        sample_count = len(self._fmeasure_buffer)
        extra = f"fast ({sample_count} samples)"
        row = [
            f"{ts:.3f}",
            iso,
            self._filter_port or "",
            self._filter_address or "",
            "measure",
            "fMeasure",
            f"{value:.5f}",
            "",
            extra,
            self._usertag or ""
        ]
        try:
            self._writer.writerow(row)
            self._fh.flush()
        except Exception as e:
            self.error.emit(f"Fast write failed: {e}")
        self._last_fast_emit = ts

    def _write_average(self, ts=None):
        if not self._fmeasure_buffer:
            return
        ts = ts or time.time()
        iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        avg_val = mean(self._fmeasure_buffer)
        row = [f"{ts:.3f}", iso, self._filter_port or "", self._filter_address or "", "measure", "fMeasure", f"{avg_val:.5f}", "", f"{len(self._fmeasure_buffer)} samples", self._usertag or ""]
        try:
            self._writer.writerow(row)
            self._fh.flush()
        except Exception as e:
            self.error.emit(f"Averaged write failed: {e}")
        self._fmeasure_buffer.clear()
        self._last_avg_time = ts

    @pyqtSlot(object)
    def on_record(self, rec):
        if self._filter_port and rec.get("port") != self._filter_port:
            return
        if self._filter_address and rec.get("address") != self._filter_address:
            return
        if rec.get("kind") == "measure":
            try:
                self._q.put_nowait(rec)
            except queue.Full:
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
            row = [f"{ts:.3f}", iso, rec.get("port", ""), rec.get("address", ""), rec.get("kind", ""), rec.get("name", ""), rec.get("value", ""), rec.get("unit", ""), rec.get("extra", ""), self._usertag or ""]
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


