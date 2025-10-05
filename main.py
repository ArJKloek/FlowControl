# propar_qt/main.py
import sys, os, time
from PyQt5 import uic, QtCore
from PyQt5.QtCore import QThread, Qt
from PyQt5.QtWidgets import (
QApplication, QMainWindow, QMessageBox, QComboBox, QWidgetAction
)

from backend.manager import ProparManager
from backend.models import NodesTableModel
from dialogs import NodeViewer
from backend.worker import TelemetryLogWorker
from backend.graph_dialog import GraphDialog
#from flowchannel import FlowChannelDialog
from backend.debug_signals import connect_once, tap_signal, attach_spy, spy_count, spy_last



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        uic.loadUi("ui/main.ui", self)

        combo = QComboBox()
        combo.addItems(["1 sec", "1 min", "5 min", "10 min", "30 min", "60 min"])
        comboBox_interval = QWidgetAction(self)
        comboBox_interval.setDefaultWidget(combo)
        self.menuFlowchannel.addAction(comboBox_interval)

        combo.setCurrentIndex(2)  # Selects the third item (indexing starts at 0)
        combo.currentIndexChanged.connect(self.on_interval_changed)
        self.comboBox_interval = combo  # Store reference for later use

        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.manager = ProparManager()
        self.model = NodesTableModel(self.manager)
        self._log_thread = None
        self._log_worker = None
        self._log_files = []
        self._interval = 5

        #self.actionOpen_scanner.triggered.connect(self.openNodeViewer)
        # menu/action wiring (adjust names to match your .ui)
        if hasattr(self, "actionOpen_scanner"):
            self.actionOpen_scanner.triggered.connect(self.openNodeViewer)
        #if hasattr(self, "actionStart_logging"):
        #    self.actionStart_logging.triggered.connect(lambda: self.start_logging())
        if hasattr(self, "actionStart_logging"):
            self.actionStart_logging.triggered.connect(
                lambda: self.start_logging_all_nodes(interval_min=self._interval)  # or 1, 15, etc.
            )
        if hasattr(self, "actionStop_logging"):
            self.actionStop_logging.triggered.connect(lambda: self.stop_logging())
            
        if hasattr(self, "actionShow_graph"):
            self.actionShow_graph.triggered.connect(self.openGraphDialog)
        
        if hasattr(self, "actionAdaptive_on"):
            self.actionAdaptive_on.triggered.connect(self.toggle_adaptive_mode)
        
        #if hasattr(self, "actionToggle_logging"):
        #    self.actionToggle_logging.triggered.connect(self.toggle_logging)

        # optional: surface poller errors in the status bar
        if hasattr(self.manager, "pollerError"):
            self.manager.pollerError.connect(lambda m: self.statusBar().showMessage(m, 4000))
    
    def on_interval_changed(self, index):
        text = self.comboBox_interval.currentText()
        value, unit = text.split()
        value = int(value)
        if unit.lower().startswith("sec"):
            interval_seconds = value
        else:
            interval_seconds = value * 60
        self._interval = interval_seconds // 60  # for display, if needed

        # Update interval for single log worker
        if self._log_worker:
            self._log_worker._interval = interval_seconds

        # Update interval for all node log workers
        if hasattr(self, "_node_log_threads"):
            for thread, worker in self._node_log_threads:
                worker._interval = interval_seconds

        self.statusBar().showMessage(f"Logging interval set to {interval_seconds} seconds")

    def toggle_adaptive_mode(self, checked):
        """Toggle adaptive fast mode on/off for all active workers."""
        # Update adaptive mode for single log worker
        if self._log_worker:
            self._log_worker.set_adaptive_enabled(checked)

        # Update adaptive mode for all node log workers
        if hasattr(self, "_node_log_threads"):
            for thread, worker in self._node_log_threads:
                worker.set_adaptive_enabled(checked)

        status = "enabled" if checked else "disabled"
        self.statusBar().showMessage(f"Adaptive logging mode {status}")

    def openGraphDialog(self, file_path=None):
        dlg = GraphDialog(self, file_path=file_path)
        dlg.show()
        # Optionally keep a reference: self._graph_dialog = dlg

    def start_logging_all_nodes(self, interval_min=1):
        self.actionStop_logging.setEnabled(True)
        self.actionStart_logging.setEnabled(False)
        if not hasattr(self, "_node_log_threads"):
            self._node_log_threads = []

        # Get nodes from scanner or model
        try:
            nodeviewer = self.findChild(NodeViewer)
            nodes = nodeviewer.model._nodes
        except Exception:
            nodes = []

        if not nodes:
            QMessageBox.warning(self, "Logging", "No connected nodes to log.")
            return

        for node in nodes:
            self.start_logging_for_node(node, interval_min=interval_min)

        self.statusBar().showMessage(f"Logging started for {len(nodes)} nodes.")

    def start_logging_for_node(self, node, interval_min):
        usertag = getattr(node, "usertag", f"{node.port}_{node.address}")
        safe_tag = "".join(c if c.isalnum() else "_" for c in str(usertag))
        stamp = time.strftime("%Y%m%d_%H%M%S")
        logname = f"log_{safe_tag}_{stamp}.csv"
        path = os.path.join(os.getcwd(), logname)
        self._log_files.append(path)  # 'path' is the log file path used in TelemetryLogWorker
        
        # Check if adaptive mode is enabled
        adaptive_enabled = self.actionAdaptive_on.isChecked() if hasattr(self, "actionAdaptive_on") else False
        
        log_worker = TelemetryLogWorker(
            path,
            filter_port=node.port,
            filter_address=node.address,
            interval_min=interval_min,
            usertag=usertag,
            adaptive_enabled=adaptive_enabled
        )
        log_thread = QThread(self)
        log_worker.moveToThread(log_thread)
        log_thread.started.connect(log_worker.run)
        self.manager.telemetry.connect(
            log_worker.on_record,
            type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection
        )
        log_worker.started.connect(lambda p: print(f"[Node Log] → {p}"))
        log_thread.start()

        # keep refs so it doesn't get GC’d
        if not hasattr(self, "_node_log_threads"):
            self._node_log_threads = []
        self._node_log_threads.append((log_thread, log_worker))




    def start_logging(self, path=None):
        if self._log_thread:
            return

        # Check if adaptive mode is enabled
        adaptive_enabled = self.actionAdaptive_on.isChecked() if hasattr(self, "actionAdaptive_on") else False

        # 1) create worker + thread first
        self._log_worker = TelemetryLogWorker(
            path or os.path.join(os.getcwd(), f"flowcontrol_log_{time.strftime('%Y%m%d_%H%M%S')}.csv"),
            adaptive_enabled=adaptive_enabled
        )
        self._log_thread = QThread(self)
        self._log_worker.moveToThread(self._log_thread)

        # 2) start the worker thread
        self._log_thread.started.connect(self._log_worker.run)

        # 3) connect telemetry -> worker
        self.manager.telemetry.connect(
            self._log_worker.on_record,
            type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection
        )

        # 4) prove connections
        print("manager.telemetry receivers:", self.manager.receivers(self.manager.telemetry))
        # optional: tee to console (you already have this)
        # tap_signal(self.manager.telemetry, "manager.telemetry")

        # UI feedback hooks...
        self._log_worker.started.connect(lambda p: self.statusBar().showMessage(f"Logging → {p}"))
        self._log_worker.error.connect(lambda m: QMessageBox.warning(self, "Logging", m))
        self._log_worker.stopped.connect(lambda p: self.statusBar().showMessage(f"Stopped logging: {p}"))

        self._log_thread.start()

        # sanity ping: this should print from [WORKER] on_record
        self.manager.telemetry.emit({
            "ts": time.time(), "port": "TEST", "address": 0,
            "kind": "test", "name": "startup", "value": 1
        })

    def stop_logging(self):
        # Stop single log worker/thread
        self.actionStop_logging.setEnabled(False)
        self.actionStart_logging.setEnabled(True)
        if self._log_thread:
            try:
                self.manager.telemetry.disconnect(self._log_worker.on_record)
            except Exception:
                pass
            self._log_worker.request_stop.emit()
            #self._log_thread.quit()
            #self._log_thread.wait(1000)
            #self._log_thread = None
            #self._log_worker = None

        # Stop all node log workers/threads
        if hasattr(self, "_node_log_threads"):
            for thread, worker in self._node_log_threads:
                try:
                    self.manager.telemetry.disconnect(worker.on_record)
                    worker.request_stop.emit()
                    #worker.stop()
                    thread.quit()
                    thread.wait(1000)
                except Exception:
                    pass
            self._node_log_threads = []

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
        try:
            self.stop_logging()
            if hasattr(self, "_node_log_threads"):
                for thread, worker in self._node_log_threads:
                    try:
                        self.manager.telemetry.disconnect(worker.on_record)
                        worker.stop()
                        thread.quit()
                        thread.wait(1000)
                    except Exception:
                        pass
        except Exception:
            pass
        if hasattr(self.manager, "stop_all_pollers"):
            try:
                self.manager.stop_all_pollers()
            except Exception:
                pass
        super().closeEvent(e)

    
def main():
    # simple CLI flag: --dummy enables dummy instrument
    if "--dummy" in sys.argv:
        os.environ["FLOWCONTROL_USE_DUMMY"] = "1"
        # remove to avoid confusing Qt argument parser
        sys.argv = [a for a in sys.argv if a != "--dummy"]
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()