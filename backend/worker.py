from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread
import csv, os, time, queue

class TelemetryLogWorker(QObject):
    error = pyqtSignal(str)
    started = pyqtSignal(str)
    stopped = pyqtSignal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        print(f"Logging to {path}")
        self._path = path
        self._q = queue.Queue(maxsize=10000)
        self._running = False
        self._fh = None
        self._writer = None
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

        try:
            while self._running:
                try:
                    rec = self._q.get(timeout=0.5)
                except queue.Empty:
                    rec = None

                if rec is None:
                    # periodic flush
                    if self._fh and self._count_since_flush:
                        self._fh.flush()
                        self._count_since_flush = 0
                    continue

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
        finally:
            try:
                if self._fh:
                    self._fh.flush()
                    self._fh.close()
            except Exception:
                pass
            self.stopped.emit(self._path)

    @pyqtSlot(object)
    def on_record(self, rec):
        # called via Qt signal (QueuedConnection) from main thread
        print(rec)
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
