from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, QTimer
import csv, os, time, queue
from statistics import mean

class TelemetryLogWorker(QObject):
    error = pyqtSignal(str)
    started = pyqtSignal(str)
    stopped = pyqtSignal(str)
    request_stop = pyqtSignal()

    def __init__(self, path=None, *, filter_port=None, filter_address=None, interval_min, usertag=None, parent=None):
        super().__init__(parent)
        self._usertag = usertag
        # Always use log_{usertag}.csv for the log file name
        data_dir = os.path.join(os.getcwd(), "Data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        if self._usertag:
            self._path = os.path.join(data_dir, f"log_{self._usertag}.csv")
        else:
            self._path = os.path.join(data_dir, "log_unknown.csv")
        self._filter_port = filter_port
        self._filter_address = filter_address
        self._interval = interval_min * 60  # convert minutes to seconds
        self._running = False
        self._q = queue.Queue()
        self._fh = None
        self._count_since_flush = 0
        self._fmeasure_buffer = []
        self._fmeasure_raw_buffer = []  # Separate buffer for raw values
        self._last_avg_time = time.time()
        self.request_stop.connect(self.stop)

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
                name = rec.get("name")
                val = rec.get("value", None)
                
                if isinstance(val, (int, float)):
                    if name == "fMeasure":
                        self._fmeasure_buffer.append(val)
                    elif name == "fMeasure_raw":
                        self._fmeasure_raw_buffer.append(val)
        except queue.Empty:
            pass

        # Calculate the rate of change or variability
        #if len(self._fmeasure_buffer) > 1:
        #    changes = [abs(self._fmeasure_buffer[i] - self._fmeasure_buffer[i - 1]) for i in range(1, len(self._fmeasure_buffer))]
        #    avg_change = sum(changes) / len(changes)

        #    # Adjust the interval based on the rate of change
        #    if avg_change > 10:  # High variability (adjust threshold as needed)
        #        self._interval = max(10, self._interval / 2)  # Decrease interval, minimum 10 seconds
        #    elif avg_change < 1:  # Low variability (adjust threshold as needed)
        #        self._interval = min(300, self._interval * 2)  # Increase interval, maximum 5 minutes

        # Write the averages if the interval has elapsed
        if now - self._last_avg_time >= self._interval and (self._fmeasure_buffer or self._fmeasure_raw_buffer):
            self._write_averages(now)

    def _write_averages(self, ts=None):
        ts = ts or time.time()
        iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        
        # Write compensated fMeasure average
        if self._fmeasure_buffer:
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
                print(f"✅ CSV: fMeasure = {avg_val:.3f} ({len(self._fmeasure_buffer)} samples)")
            except Exception as e:
                self.error.emit(f"fMeasure averaged write failed: {e}")
            
            self._fmeasure_buffer.clear()
        
        # Write raw fMeasure_raw average
        if self._fmeasure_raw_buffer:
            avg_raw_val = mean(self._fmeasure_raw_buffer)
            
            row = [
                f"{ts:.3f}",
                iso,
                self._filter_port or "",
                self._filter_address or "",
                "measure",
                "fMeasure_raw",
                f"{avg_raw_val:.5f}",
                "",
                f"{len(self._fmeasure_raw_buffer)} samples",
                self._usertag or ""
            ]
            
            try:
                self._writer.writerow(row)
                print(f"✅ CSV: fMeasure_raw = {avg_raw_val:.3f} ({len(self._fmeasure_raw_buffer)} samples)")
            except Exception as e:
                self.error.emit(f"fMeasure_raw averaged write failed: {e}")
            
            self._fmeasure_raw_buffer.clear()
        
        # Flush the file
        try:
            self._fh.flush()
        except Exception as e:
            self.error.emit(f"File flush failed: {e}")
        
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
            print(f"✅ CSV: {rec.get('kind')}:{rec.get('name')} = {rec.get('value')}")
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


