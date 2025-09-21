# propar_qt/manager.py
from typing import Dict, List, Optional, Tuple
import threading
from contextlib import contextmanager
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt
from PyQt5 import QtCore
from propar_new import master as ProparMaster, instrument as ProparInstrument
from .types import NodeInfo
from .scanner import ProparScanner
import time

from .poller import PortPoller
from window_tiler import DialogTiler


class ProparManager(QObject):
    nodeAdded = pyqtSignal(object) # NodeInfo
    scanProgress = pyqtSignal(str) # port
    scanError = pyqtSignal(str, str) # port, error
    scanFinished = pyqtSignal()
    
    measured = pyqtSignal(object)   # emits float or None
    pollerError = pyqtSignal(str)  # emits error message
    telemetry = pyqtSignal(object)  # emits dict with telemetry data

    def __init__(self, parent: Optional[QObject] = None, baudrate: int = 38400):
        super().__init__(parent)
        self._baudrate = baudrate
        self._masters: Dict[str, ProparMaster] = {}
        self._nodes: List[NodeInfo] = []
        self._scanner: Optional[ProparScanner] = None
        self._pollers: Dict[str, Tuple[QThread, PortPoller]] = {}
        self._port_locks: Dict[str, threading.RLock] = {}
        self.tiler = DialogTiler()


    # manager.py — inside class ProparManager
    def start_parallel_polling(self, default_period: float = 0.2):
        """
        Ensure one PortPoller per port and register all discovered nodes on it.
        Safe to call multiple times; add_node() ignores duplicates.
        """
        for info in list(self._nodes):  # NodeInfo(port, address, ...)
            poller = self.ensure_poller(info.port, default_period=default_period)
            poller.add_node(info.address, period=default_period)

    def stop_parallel_polling(self):
        self.stop_all_pollers()


    # ---- Accessors ----
    def masters(self) -> Dict[str, ProparMaster]:
        return self._masters


    def nodes(self) -> List[NodeInfo]:
        return list(self._nodes)


    def clear(self):
        self._nodes.clear()
        # Keep masters cached for reuse. Provide a separate close_all() if desired.


    # ---- Scanning ----
    def scan(self, ports: Optional[List[str]] = None):
        if self._scanner and self._scanner.isRunning():
            return # already scanning
        self.close_all_ports()
        time.sleep(0.2)  # Add a small delay
        self.clear()
        self._scanner = ProparScanner(ports=ports, baudrate=self._baudrate)
        self._scanner.startedPort.connect(self.scanProgress)
        self._scanner.portError.connect(self.scanError)
        self._scanner.nodeFound.connect(self._onNodeFound)
        self._scanner.finishedScanning.connect(self._onScanFinished)
        self._scanner.start()


    def stop_scan(self):
        if self._scanner and self._scanner.isRunning():
            self._scanner.stop()
            self._scanner.wait()

    def close_all_ports(self):
        for master in self._masters.values():
            try:
                master.close()  # Or master.serial.close(), depending on your ProparMaster implementation
            except Exception:
                pass
        self._masters.clear()


    def _onNodeFound(self, info: NodeInfo):
        self._nodes.append(info)
        # Lazily cache a master per port for faster instrument creation later
        if info.port not in self._masters:
            try:
                self._masters[info.port] = ProparMaster(info.port, baudrate=self._baudrate)
            except Exception:
            # We'll retry on demand inside instrument()
                pass
        self.nodeAdded.emit(info)


    def _onScanFinished(self):
        self.scanFinished.emit()


    ## ---- Instruments ----
    #def instrument(self, port: str, address: int, channel: int = 1) -> ProparInstrument:
    #    if port not in self._masters:
    #        self._masters[port] = ProparMaster(port, baudrate=self._baudrate)
    #    return ProparInstrument(port, address=address, baudrate=self._baudrate, channel=channel)
    # ---- Instruments (ad-hoc) ----
    def instrument(self, port: str, address: int, channel: int = 1) -> ProparInstrument:
        """
        Prefer using the PortPoller for recurring reads/writes.
        If you use this for ad-hoc ops, guard with port_lock(port).
        """
        if port not in self._masters:
            self._masters[port] = ProparMaster(port, baudrate=self._baudrate)
        return ProparInstrument(port, address=address, baudrate=self._baudrate, channel=channel)

    # ---- New: per-port poller management ----
    def ensure_poller(self, port: str, default_period: float = 0.5) -> PortPoller:
        """Create or return the single PortPoller for this port."""
        if port in self._pollers:
            return self._pollers[port][1]
        # make sure master exists (poller will use instrument(...))
        if port not in self._masters:
            self._masters[port] = ProparMaster(port, baudrate=self._baudrate)
        t = QThread(self)
        poller = PortPoller(self, port, default_period=default_period)
        poller.moveToThread(t)
        t.started.connect(poller.run)
        # bubble signals up
        poller.measured.connect(self.measured, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        poller.error.connect(self._on_poller_error, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        poller.telemetry.connect(self.telemetry, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)  # NEW
        t.start()
        self._pollers[port] = (t, poller)
        # init lock for this port if not present
        self._port_locks.setdefault(port, threading.RLock())
        return poller

    def _on_poller_error(self, msg: str):
        self.pollerError.emit(msg)

    def register_node_for_polling(self, port: str, address: int, period: Optional[float] = None):
        poller = self.ensure_poller(port)
        poller.add_node(address, period=period)

    def unregister_node_from_polling(self, port: str, address: int):
        if port in self._pollers:
            self._pollers[port][1].remove_node(address)

    def request_setpoint_flow(self, port: str, address: int, flow_value: float):
        poller = self.ensure_poller(port)
        poller.request_setpoint_flow(int(address), float(flow_value))

    def request_setpoint_pct(self, port: str, address: int, pct_value: float):
        poller = self.ensure_poller(port)
        poller.request_setpoint_pct(int(address), float(pct_value))
    
    def request_usertag(self, port: str, address: int, usertag: str):
        poller = self.ensure_poller(port)
        poller.request_usertag(int(address), str(usertag))



    def request_fluid_change(self, port: str, address: int, new_index: int):
        """Route writes through the poller so they serialize with polling."""
        poller = self.ensure_poller(port)
        poller.request_fluid_change(address, int(new_index))

    def stop_all_pollers(self):
        for port, (t, poller) in list(self._pollers.items()):
            try:
                poller.stop()
                t.quit()
                t.wait(1000)
            except Exception:
                pass
        self._pollers.clear()

    # ---- Optional: port-wide lock for legacy I/O ----
    @contextmanager
    def port_lock(self, port: str):
        lock = self._port_locks.setdefault(port, threading.RLock())
        lock.acquire()
        try:
            yield
        finally:
            lock.release()