# propar_qt/main.py
import sys, os, time
from PyQt5 import uic, QtCore
from PyQt5.QtCore import QThread, Qt
from PyQt5.QtWidgets import (
QApplication, QMainWindow, QMessageBox
)

from backend.manager import ProparManager
from backend.models import NodesTableModel
from dialogs import NodeViewer
from backend.worker import TelemetryLogWorker
#from flowchannel import FlowChannelDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        uic.loadUi("ui/main.ui", self)

        self.manager = ProparManager()
        self.model = NodesTableModel(self.manager)
        self._log_thread = None
        self._log_worker = None
        #self.actionOpen_scanner.triggered.connect(self.openNodeViewer)
        # menu/action wiring (adjust names to match your .ui)
        if hasattr(self, "actionOpen_scanner"):
            self.actionOpen_scanner.triggered.connect(self.openNodeViewer)
        if hasattr(self, "actionStart_logging"):
            self.actionStart_logging.triggered.connect(lambda: self.start_logging())
        if hasattr(self, "actionStop_logging"):
            self.actionStop_logging.triggered.connect(self.stop_logging)
        #if hasattr(self, "actionToggle_logging"):
        #    self.actionToggle_logging.triggered.connect(self.toggle_logging)

        # optional: surface poller errors in the status bar
        if hasattr(self.manager, "pollerError"):
            self.manager.pollerError.connect(lambda m: self.statusBar().showMessage(m, 4000))
            
    def start_logging(self, path=None):
        if self._log_thread:
            return  # already running
        if path is None:
            # default filename with date/time
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(os.getcwd(), f"flowcontrol_log_{stamp}.csv")

        self._log_thread = QThread(self)
        self._log_worker = TelemetryLogWorker(path)
        self._log_worker.moveToThread(self._log_thread)

        self._log_thread.started.connect(self._log_worker.run)
        # Subscribe once (UniqueConnection avoids duplicates)
        self.manager.telemetry.connect(
            self._log_worker.on_record,
            type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection
        )

        # Optional status hooks
        self._log_worker.started.connect(lambda p: self.statusBar().showMessage(f"Logging → {p}"))
        self._log_worker.error.connect(lambda m: QMessageBox.warning(self, "Logging", m))
        self._log_worker.stopped.connect(lambda p: self.statusBar().showMessage(f"Stopped logging: {p}"))

        self._log_thread.start()
        # sanity ping to verify the signal/slot path
        self.manager.telemetry.emit({
            "ts": time.time(), "port": "TEST", "address": 0,
            "kind": "test", "name": "startup", "value": 1
        })
    def stop_logging(self):
        if not self._log_thread:
            return
        try:
            self.manager.telemetry.disconnect(self._log_worker.on_record)
        except Exception:
            pass
        self._log_worker.stop()
        self._log_thread.quit()
        self._log_thread.wait(1000)
        self._log_thread = None
        self._log_worker = None

    def toggle_logging(self, checked=None):
        if self._log_thread:
            self.stop_logging()
        else:
            self.start_logging()
    
    def openNodeViewer(self):
        dlg = NodeViewer(self.manager, self)
        
        #dlg.nodesSelected.connect(self.openFlowChannels)
        dlg.show()

    #def openFlowChannels(self, node_list):
    #    FlowChannelDialog(self.manager, node_list, self).exec_()
    def closeEvent(self, e):
        # stop logging cleanly
        try:
            self.stop_logging()
        except Exception:
            pass
        # (optional) stop pollers if your manager exposes it
        if hasattr(self.manager, "stop_all_pollers"):
            try:
                self.manager.stop_all_pollers()
            except Exception:
                pass
        super().closeEvent(e)
    
def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()