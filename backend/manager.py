# propar_qt/manager.py
from typing import Dict, List, Optional, Tuple
import threading
import time
from contextlib import contextmanager
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt
from PyQt5 import QtCore
from propar_new import master as ProparMaster
from .types import NodeInfo
from .dummy_instrument import DummyInstrument
import os
from .scanner import ProparScanner
from .error_logger import ErrorLogger

from .poller import PortPoller


class ManagedInstrument:
    """Lightweight instrument facade that always uses a manager-owned master."""

    def __init__(self, master, port: str, address: int, channel: int = 1):
        self.master = master
        self.port = port
        self.address = int(address)
        self.channel = int(channel)
        self.db = master.db

    def _param(self, dde_nr: int, data=None, with_data: bool = False):
        p = dict(self.db.get_parameter(int(dde_nr)))
        p["node"] = self.address
        if with_data:
            p["data"] = data
        return p

    def readParameter(self, dde_nr: int, channel=None):
        try:
            res = self.master.read_parameters([self._param(dde_nr)]) or []
            if res and res[0].get("status", 1) == 0:
                val = res[0].get("data")
                if isinstance(val, str):
                    return val.strip()
                return val
        except Exception:
            pass
        return None

    def writeParameter(self, dde_nr: int, data, channel=None, verify=False, tol=None, debug=False):
        ok = False
        try:
            res = self.master.write_parameters([self._param(dde_nr, data, with_data=True)])
            if res is True or res == 0:
                ok = True
            elif isinstance(res, dict):
                ok = (res.get("status", 1) == 0)
            elif isinstance(res, (list, tuple)):
                ok = all(
                    (isinstance(x, dict) and x.get("status", 1) == 0) or (isinstance(x, int) and x == 0)
                    for x in res
                )
        except Exception:
            ok = False

        if verify and not ok:
            rb = self.readParameter(dde_nr, channel=channel)
            if isinstance(data, float) and isinstance(rb, (int, float)):
                abs_tol = tol if tol is not None else 1e-3 * max(1.0, abs(float(data)))
                ok = abs(float(rb) - float(data)) <= abs_tol
            else:
                ok = (rb == data)

        return ok

    def read_parameters(self, parameters):
        params = [dict(p) for p in parameters]
        for p in params:
            p["node"] = self.address
        return self.master.read_parameters(params)

    @property
    def measure(self):
        return self.readParameter(8)

    @property
    def id(self):
        return self.readParameter(1)


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
        self._masters: Dict[str, Optional[ProparMaster]] = {}
        self._nodes: List[NodeInfo] = []
        self._scanner: Optional[ProparScanner] = None
        self._pollers: Dict[str, Tuple[QThread, PortPoller]] = {}
        self._port_locks: Dict[str, threading.RLock] = {}
        self._instrument_cache: Dict[Tuple[str, int, int], ManagedInstrument] = {}
        
        # Initialize error logger
        self.error_logger = ErrorLogger(self)


    # manager.py — inside class ProparManager
    def start_parallel_polling(self, default_period: float = 0.5):
        """
        Ensure one PortPoller per port and register all discovered nodes on it.
        Safe to call multiple times.
        """
        port_counts: Dict[str, int] = {}
        for info in self._nodes:
            port_counts[info.port] = port_counts.get(info.port, 0) + 1

        for info in list(self._nodes):  # NodeInfo(port, address, ...)
            min_period = 0.8 if port_counts.get(info.port, 0) >= 3 else 0.5
            effective_period = max(float(default_period), min_period)
            poller = self.ensure_poller(info.port, default_period=effective_period)
            poller.add_node(info.address, period=effective_period)

    def stop_parallel_polling(self):
        self.stop_all_pollers()


    # ---- Accessors ----
    def masters(self) -> Dict[str, Optional[ProparMaster]]:
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
        self.stop_scan()
        self.stop_all_pollers()

        stopped_ports: List[str] = []
        for port, master in list(self._masters.items()):
            if master is None:
                stopped_ports.append(port)
                continue
            try:
                master.stop()
                stopped_ports.append(port)
            except Exception as e:
                self.pollerError.emit(f"Failed to stop master on {port}: {e}")

        for port in stopped_ports:
            self._masters.pop(port, None)

        self._instrument_cache = {
            k: v for k, v in self._instrument_cache.items() if k[0] not in stopped_ports
        }


    def _onNodeFound(self, info: NodeInfo):
        self._nodes.append(info)
        self.nodeAdded.emit(info)


    def _onScanFinished(self):
        self.scanFinished.emit()


    ## ---- Instruments ----
    #def instrument(self, port: str, address: int, channel: int = 1) -> ProparInstrument:
    #    if port not in self._masters:
    #        self._masters[port] = ProparMaster(port, baudrate=self._baudrate)
    #    return ProparInstrument(port, address=address, baudrate=self._baudrate, channel=channel)
    # ---- Instruments (ad-hoc) ----
    def instrument(self, port: str, address: int, channel: int = 1):
        """
        Prefer using the PortPoller for recurring reads/writes.
        If you use this for ad-hoc ops, guard with port_lock(port).
        """
        # Dummy path first
        if os.environ.get("FLOWCONTROL_USE_DUMMY") and port.startswith("DUMMY"):
            # cache a pseudo master entry to keep logic consistent
            if port not in self._masters:
                self._masters[port] = None  # marker
            # Reuse or create one dummy per (port,address)
            key = (port, int(address))
            if not hasattr(self, "_dummy_cache"):
                self._dummy_cache = {}
            inst = self._dummy_cache.get(key)
            if inst is None:
                # Use DummyMeterInstrument for DMFM, link to DMFCs
                from .dummy_instrument import DummyInstrument
                if hasattr(self, "_dummy_instruments") and key in self._dummy_instruments:
                    inst = self._dummy_instruments[key]
                else:
                    # If DMFM, link to both DMFCs
                    if address == 2:
                        # Find DMFC dummies
                        dmfc_key1 = (port, 1)
                        dmfc_key2 = (port, 3)
                        dmfc_inst1 = self._dummy_cache.get(dmfc_key1)
                        if dmfc_inst1 is None:
                            dmfc_inst1 = DummyInstrument(port=port, address=1)
                            self._dummy_cache[dmfc_key1] = dmfc_inst1
                        dmfc_inst2 = self._dummy_cache.get(dmfc_key2)
                        if dmfc_inst2 is None:
                            dmfc_inst2 = DummyInstrument(port=port, address=3)
                            self._dummy_cache[dmfc_key2] = dmfc_inst2
                        class DummyMeterInstrument(DummyInstrument):
                            def _simulate_fmeasure(self):
                                dmfc1 = self._linked_dmfc1
                                dmfc2 = self._linked_dmfc2
                                val1 = dmfc1._simulate_fmeasure() if dmfc1 else 0.0
                                val2 = dmfc2._simulate_fmeasure() if dmfc2 else 0.0
                                return val1 + val2
                        inst = DummyMeterInstrument(port=port, address=address)
                        inst._linked_dmfc1 = dmfc_inst1
                        inst._linked_dmfc2 = dmfc_inst2
                    else:
                        inst = DummyInstrument(port=port, address=address)
                self._dummy_cache[key] = inst
            return inst

        key = (port, int(address), int(channel))
        inst = self._instrument_cache.get(key)
        if inst is not None:
            return inst

        master = self.get_or_create_master(port)
        inst = ManagedInstrument(master, port=port, address=address, channel=channel)
        self._instrument_cache[key] = inst
        return inst

    def get_or_create_master(self, port: str) -> Optional[ProparMaster]:
        """Single authority for creating or retrieving a live master per port."""
        if os.environ.get("FLOWCONTROL_USE_DUMMY") and port.startswith("DUMMY"):
            self._masters[port] = None
            return None

        cached = self._masters.get(port)
        if cached is not None:
            return cached

        master = ProparMaster(port, baudrate=self._baudrate)
        # Shared-bus defaults: avoid false disconnects from aggressive timeouts.
        master.response_timeout = max(getattr(master, "response_timeout", 0.25), 0.25)
        try:
            master.propar.serial.timeout = max(float(master.propar.serial.timeout), 0.02)
        except Exception:
            pass
        self._masters[port] = master
        return master

    # ---- New: per-port poller management ----
    def ensure_poller(self, port: str, default_period: float = 0.5) -> PortPoller:
        """Create or return the single PortPoller for this port."""
        if port in self._pollers:
            return self._pollers[port][1]
        if not (os.environ.get("FLOWCONTROL_USE_DUMMY") and port.startswith("DUMMY")):
            self.get_or_create_master(port)
        t = QThread(self)
        poller = PortPoller(self, port, default_period=max(float(default_period), 0.5))
        poller.moveToThread(t)
        t.started.connect(poller.run)
        # bubble signals up with validation
        poller.measured.connect(self._on_measurement_received, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        poller.error.connect(self._on_poller_error, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        poller.telemetry.connect(self.telemetry, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)  # NEW
        t.start()
        self._pollers[port] = (t, poller)
        # init lock for this port if not present
        self._port_locks.setdefault(port, threading.RLock())
        return poller

    def _on_poller_error(self, msg: str):
        self.pollerError.emit(msg)

    def _on_measurement_received(self, payload):
        """Validate measurements before forwarding to UI. Discard extreme measurements."""
        
        if not isinstance(payload, dict):
            # Forward non-dict payloads directly
            self.measured.emit(payload)
            return
            
        # Extract measurement data
        port = payload.get("port")
        address = payload.get("address") 
        data = payload.get("data", {})
        fmeasure = data.get("fmeasure")  # This is the actual flow value that can be extreme
        
        # Early validation: check if fmeasure is extreme
        if fmeasure is not None and port and address is not None:
            # Check if the fmeasure value is extremely high (>= 1e6)
            if fmeasure >= 1000000.0:
                # Log the extreme value error with instrument details
                instrument_info = self._get_instrument_info(port, address)
                self.error_logger.log_extreme_value_error(
                    port=port,
                    address=address,
                    extreme_value=fmeasure,
                    instrument_info=instrument_info
                )
                # Discard this extreme measurement - don't forward to UI
                return  # Exit early, don't emit this measurement
        
        # If we get here, the measurement is valid - forward to UI
        self.measured.emit(payload)
    
    def _get_instrument_info(self, port: str, address: int) -> dict:
        """Get instrument information for error logging."""
        for node in self._nodes:
            if node.port == port and node.address == address:
                return {
                    'model': getattr(node, 'model', ''),
                    'serial': getattr(node, 'serial', ''),
                    'usertag': getattr(node, 'usertag', '')
                }
        return {'model': '', 'serial': '', 'usertag': ''}

    def register_node_for_polling(self, port: str, address: int, period: Optional[float] = None):
        safe_period = max(float(period if period is not None else 0.5), 0.5)
        poller = self.ensure_poller(port, default_period=safe_period)
        poller.add_node(address, period=safe_period)

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