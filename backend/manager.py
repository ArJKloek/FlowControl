# propar_qt/manager.py
from typing import Dict, List, Optional


from PyQt5.QtCore import QObject, pyqtSignal


from propar_new import master as ProparMaster, instrument as ProparInstrument
from .types import NodeInfo
from .scanner import ProparScanner




class ProparManager(QObject):
    nodeAdded = pyqtSignal(object) # NodeInfo
    scanProgress = pyqtSignal(str) # port
    scanError = pyqtSignal(str, str) # port, error
    scanFinished = pyqtSignal()


    def __init__(self, parent: Optional[QObject] = None, baudrate: int = 38400):
        super().__init__(parent)
        self._baudrate = baudrate
        self._masters: Dict[str, ProparMaster] = {}
        self._nodes: List[NodeInfo] = []
        self._scanner: Optional[ProparScanner] = None


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


    # ---- Instruments ----
    def instrument(self, port: str, address: int, channel: int = 1) -> ProparInstrument:
        if port not in self._masters:
            self._masters[port] = ProparMaster(port, baudrate=self._baudrate)
        return ProparInstrument(port, address=address, baudrate=self._baudrate, channel=channel)