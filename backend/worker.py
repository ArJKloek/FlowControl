from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, QTimer
import csv, os, time, queue

class TelemetryLogWorker(QObject):
    error = pyqtSignal(str)
    started = pyqtSignal(str)
    stopped = pyqtSignal(str)

    def __init__(self, path, *, filter_port=None, filter_address=None, parent=None):
        super().__init__(parent)
        self._path = path
        self._filter_port = filter_port
        self._filter_address = filter_address
        self._running = False
        self._q = queue.Queue()
        self._fh = None
        self._count_since_flush = 0

    @pyqtSlot()
    def run(self):
        try:
            is_new = not os.path.exists(self._path)
            self._fh = open(self._path, "a", newline="")
            self._writer = csv.writer(self._fh)
            if is_new:
                self._writer.writerow(["ts","iso","port","address","kind","name","value","unit","extra"])
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

        try:
            while not self._q.empty():
                rec = self._q.get_nowait()

                iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rec.get("ts", time.time())))
                row = [
                    f'{rec.get("ts", ""):.3f}' if isinstance(rec.get("ts"), (int,float)) else rec.get("ts",""),
                    iso,
                    rec.get("port",""),
                    rec.get("address",""),
                    rec.get("kind",""),
                    rec.get("name",""),
                    rec.get("value",""),
                    rec.get("unit",""),
                    rec.get("extra","") if isinstance(rec.get("extra",""), str) else str(rec.get("extra",""))
                ]
                try:
                    self._writer.writerow(row)
                    self._count_since_flush += 1
                    if self._count_since_flush >= 100:
                        self._fh.flush()
                        self._count_since_flush = 0
                except Exception as e:
                    self.error.emit(f"Write failed: {e}")

        except queue.Empty:
            pass


    @pyqtSlot(object)
    def on_record(self, rec):
        # called via Qt signal (QueuedConnection) from main thread
        # Filter based on port and/or address if set
        if self._filter_port and rec.get("port") != self._filter_port:
            return
        if self._filter_address and rec.get("address") != self._filter_address:
            return
            
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


