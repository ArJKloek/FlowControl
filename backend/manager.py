# propar_qt/manager.py
from typing import Dict, List, Optional, Tuple
import threading
import json
import os
from contextlib import contextmanager
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5 import QtCore
from propar import master as ProparMaster
from .types import NodeInfo
from .scanner import ProparScanner
import time
from .error_logger import ErrorLogger
from .poller import PortPoller
from .constants import GAS_FACTORS_FILE


class ManagedInstrument:
    """Instrument facade that always uses the manager-owned master for a port."""

    def __init__(self, master: ProparMaster, port: str, address: int, channel: int = 1):
        self.master = master
        self.port = port
        self.address = int(address)
        self.channel = int(channel)
        self.db = master.db

    def _param(self, dde_nr: int, value=None, with_data: bool = False):
        p = dict(self.db.get_parameter(int(dde_nr)))
        p["node"] = self.address
        if with_data:
            p["data"] = value
        return p

    def readParameter(self, dde_nr: int, channel=None):
        try:
            res = self.master.read_parameters([self._param(dde_nr)]) or []
            if res and res[0].get("status", 1) == 0:
                val = res[0].get("data")
                return val.strip() if isinstance(val, str) else val
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
                ok = res.get("status", 1) == 0
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
        # Shared instrument cache per port to avoid conflicts on shared USB devices
        self._shared_inst_cache: Dict[str, Dict[int, ManagedInstrument]] = {}
        # Initialize the ErrorLogger
        self.error_logger = ErrorLogger(self)
        # Gas factor storage: {(port, address): factor} - temporary in-memory
        self._gas_factors: Dict[Tuple[str, int], float] = {}
        # Persistent gas factor storage by serial number: {serial_nr: factor}
        self._gas_factors_file = GAS_FACTORS_FILE
        self._persistent_gas_factors: Dict[str, float] = {}
        self._load_gas_factors()


    # manager.py — inside class ProparManager
    def start_parallel_polling(self, default_period: float = 0.5):
        """
        Ensure one PortPoller per port and register all discovered nodes on it.
        Safe to call multiple times; add_node() ignores duplicates.
        """
        per_port_counts: Dict[str, int] = {}
        for info in self._nodes:
            per_port_counts[info.port] = per_port_counts.get(info.port, 0) + 1

        for info in list(self._nodes):
            min_period = 0.8 if per_port_counts.get(info.port, 0) >= 3 else 0.5
            safe_period = max(float(default_period), min_period)
            poller = self.ensure_poller(info.port, default_period=safe_period)
            poller.add_node(info.address, period=safe_period)

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
        self.stop_scan()
        self.stop_all_pollers()

        closed_ports = []
        for port, master in list(self._masters.items()):
            try:
                master.stop()
                closed_ports.append(port)
            except Exception as e:
                self.pollerError.emit(f"Failed to stop master on {port}: {e}")

        for port in closed_ports:
            self._masters.pop(port, None)
            self._shared_inst_cache.pop(port, None)


    def _onNodeFound(self, info: NodeInfo):
        self._nodes.append(info)
        self.nodeAdded.emit(info)


    def _onScanFinished(self):
        self.scanFinished.emit()

    def _get_or_create_master(self, port: str) -> ProparMaster:
        """Single authority for master creation so one live owner exists per serial port."""
        master = self._masters.get(port)
        if master is not None:
            return master

        master = ProparMaster(port, baudrate=self._baudrate)
        master.response_timeout = max(getattr(master, "response_timeout", 0.25), 0.25)
        try:
            master.propar.serial.timeout = max(float(master.propar.serial.timeout), 0.02)
        except Exception:
            pass
        self._masters[port] = master
        return master


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
        return self.get_shared_instrument(port, address, channel)

    def get_shared_instrument(self, port: str, address: int, channel: int = 1):
        """
        Get a shared instrument instance with proper caching and locking for shared USB devices.
        This prevents multiple instrument instances from conflicting on the same port.
        Enhanced with connection error handling and recovery.
        """
        with self.port_lock(port):
            # Initialize port cache if needed
            if port not in self._shared_inst_cache:
                self._shared_inst_cache[port] = {}
            
            # Check if instrument already exists in cache
            if address in self._shared_inst_cache[port]:
                cached_inst = self._shared_inst_cache[port][address]
                
                # Verify the cached instrument is still valid
                try:
                    # Quick test to see if the connection is still alive
                    if hasattr(cached_inst.master, 'propar') and hasattr(cached_inst.master.propar, 'serial'):
                        serial_port = cached_inst.master.propar.serial
                        if serial_port and serial_port.is_open:
                            return cached_inst
                        else:
                            # Connection is dead, remove from cache
                            del self._shared_inst_cache[port][address]
                except Exception:
                    # Any error checking connection, remove from cache
                    self._shared_inst_cache[port].pop(address, None)
            
            # Create new instrument and cache it
            try:
                master = self._get_or_create_master(port)
                inst = ManagedInstrument(master, port=port, address=address, channel=channel)
                
                # Test the connection before caching
                try:
                    # Connection recovery test
                    if hasattr(inst.master, 'propar') and hasattr(inst.master.propar, 'serial'):
                        if not inst.master.propar.serial.is_open:
                            # Attempt to reopen the connection
                            try:
                                inst.master.propar.serial.open()
                                if self.error_logger:
                                    self.error_logger.log_error(
                                        port,
                                        address,
                                        "CONNECTION_RECOVERY",
                                        f"Successfully reopened serial port {port}"
                                    )
                            except Exception as reopen_error:
                                # Clear cache and let it be recreated
                                if port in self._shared_inst_cache:
                                    if address in self._shared_inst_cache[port]:
                                        del self._shared_inst_cache[port][address]
                                raise Exception(f"Failed to reopen serial port: {reopen_error}")
                except Exception as e:
                    if self.error_logger:
                        self.error_logger.log_error(
                            port,
                            address,
                            "CONNECTION_FAILED",
                            f"Connection test failed: {e}"
                        )
                    # Clear cache entry and propagate error for recreation attempt
                    if port in self._shared_inst_cache:
                        if address in self._shared_inst_cache[port]:
                            del self._shared_inst_cache[port][address]
                    raise Exception(f"Connection test failed: {e}")
                
                self._shared_inst_cache[port][address] = inst
                return inst
                
            except Exception as e:
                # If instrument creation fails, try to recreate the master
                error_msg = str(e).lower()
                if any(err in error_msg for err in ["bad file descriptor", "errno 9", "device not found", "port not open"]):
                    try:
                        # Force reconnection
                        self.force_reconnect_port(port)
                        # Try once more with new master
                        master = self._get_or_create_master(port)
                        inst = ManagedInstrument(master, port=port, address=address, channel=channel)
                        self._shared_inst_cache[port][address] = inst
                        return inst
                    except Exception:
                        pass  # If second attempt fails, re-raise original error
                
                # Re-raise the original error
                raise

    def clear_shared_instrument_cache(self, port: str, address: Optional[int] = None):
        """Clear shared instrument cache for port reconnection after errors."""
        with self.port_lock(port):
            if port in self._shared_inst_cache:
                if address is not None:
                    # Clear specific address
                    self._shared_inst_cache[port].pop(address, None)
                else:
                    # Clear entire port cache
                    self._shared_inst_cache[port].clear()

    def force_reconnect_port(self, port: str):
        """Force reconnection of a port by clearing cache and recreating master."""
        try:
            with self.port_lock(port):
                # Clear all cached instruments for this port
                if port in self._shared_inst_cache:
                    self._shared_inst_cache[port].clear()
                
                # Close and recreate the master connection
                if port in self._masters:
                    try:
                        old_master = self._masters[port]
                        if hasattr(old_master, 'stop'):
                            old_master.stop()
                    except Exception:
                        pass  # Ignore errors when closing
                    
                    self._masters.pop(port, None)
                    self._get_or_create_master(port)
                    print(f"Reconnected master for port {port}")
                
        except Exception as e:
            print(f"Failed to reconnect port {port}: {e}")

    # ---- New: per-port poller management ----
    def ensure_poller(self, port: str, default_period: float = 0.5) -> PortPoller:
        """Create or return the single PortPoller for this port."""
        if port in self._pollers:
            return self._pollers[port][1]
        self._get_or_create_master(port)
        t = QThread(self)
        poller = PortPoller(self, port, default_period=max(float(default_period), 0.5))
        poller.moveToThread(t)
        t.started.connect(poller.run)
        # bubble signals up
        poller.measured.connect(self.measured, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        poller.error.connect(self._on_poller_error, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        poller.error_occurred.connect(self._on_poller_error, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        poller.telemetry.connect(self._on_telemetry, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)  # NEW - with error logging
        t.start()
        self._pollers[port] = (t, poller)
        # init lock for this port if not present
        self._port_locks.setdefault(port, threading.RLock())
        return poller

    def _on_telemetry(self, telemetry_data: dict):
        """Handle telemetry events and log validation errors."""
        # Forward to main telemetry signal
        self.telemetry.emit(telemetry_data)
        
        # Check for validation errors and log them
        try:
            if (telemetry_data.get("kind") == "validation_skip" and 
                telemetry_data.get("name") == "dmfc_capacity_exceeded"):
                
                port = telemetry_data.get("port", "unknown")
                address = telemetry_data.get("address", "unknown")
                value = telemetry_data.get("value", 0)
                capacity = telemetry_data.get("capacity", 0)
                threshold = telemetry_data.get("threshold", 0)
                reason = telemetry_data.get("reason", "Capacity validation failed")
                
                # Log this as a validation error
                self.log_validation_error(
                    port=port,
                    address=int(address) if str(address).isdigit() else 0,
                    parameter="FMEASURE",
                    value=value,
                    limit=threshold,
                    details=f"Capacity: {capacity} | Threshold: {threshold} | Reason: {reason}"
                )
                
        except Exception as e:
            print(f"Error processing telemetry for error logging: {e}")

    def log_instrument_error(self, port: str, address: int, error_type: str, message: str, details: str = ""):
        """Log an instrument error with full context."""
        instrument_info = self._get_instrument_info(port, address)
        self.error_logger.log_error(
            port=port,
            address=str(address),
            error_type=error_type,
            error_message=message,
            error_details=details,
            instrument_info=instrument_info
        )
    
    def log_validation_error(self, port: str, address: int, parameter: str, value: float, limit: float, details: str = ""):
        """Log a validation error (e.g., capacity exceedance)."""
        instrument_info = self._get_instrument_info(port, address)
        message = f"{parameter} value {value} exceeds limit {limit}"
        self.error_logger.log_error(
            port=port,
            address=str(address),
            error_type="validation",
            error_message=message,
            error_details=details,
            instrument_info=instrument_info,
            measurement_data={parameter.lower(): value}
        )
    
    def log_setpoint_error(self, port: str, address: int, setpoint: float, details: str = ""):
        """Log a setpoint error."""
        instrument_info = self._get_instrument_info(port, address)
        self.error_logger.log_setpoint_error(
            port=port,
            address=str(address),
            setpoint_value=setpoint,
            error_message=details,
            instrument_info=instrument_info
        )

    def _get_instrument_info(self, port: str, address: int) -> dict:
        """Get instrument information for error logging."""
        try:
            # Look for the device in our device list
            for device in self._devices:
                if device.get('port') == port and device.get('address') == address:
                    # Build detailed instrument info dict
                    info = {}
                    
                    # Add available device information
                    if device.get('device_type'):
                        info['model'] = device.get('device_type', '')
                    
                    if device.get('serial_number'):
                        info['serial'] = device.get('serial_number', '')
                    
                    if device.get('usertag'):
                        info['usertag'] = device.get('usertag', '')
                    
                    # Add additional context
                    if device.get('capacity'):
                        info['capacity'] = device.get('capacity', '')
                    
                    if device.get('fluid_name'):
                        info['fluid'] = device.get('fluid_name', '')
                    
                    return info
                    
            # If not found in devices, return basic info
            return {'model': 'Unknown', 'serial': '', 'usertag': ''}
            
        except Exception as e:
            # If anything fails, return basic info
            return {'model': 'Unknown', 'serial': '', 'usertag': '', 'error': str(e)}

    def _on_poller_error(self, msg: str):
        """Handle poller errors and log them with instrument details."""
        self.pollerError.emit(msg)
        
        # Extract port and address from error message if possible
        try:
            # Try to parse format like "COM3/5: error message" or "/dev/ttyUSB0/5: error message"
            if "/" in msg and ":" in msg:
                port_addr = msg.split(":")[0].strip()
                if "/" in port_addr:
                    # Handle different port formats:
                    # Windows: "COM3/5" -> port="COM3", address="5"
                    # Linux: "/dev/ttyUSB0/5" -> port="/dev/ttyUSB0", address="5"
                    
                    # Split from the right to get the last part as address
                    parts = port_addr.rsplit("/", 1)
                    if len(parts) == 2:
                        port, address_str = parts
                        
                        # Try to convert address to integer
                        try:
                            address = int(address_str)
                            
                            # Determine error type from message content
                            error_type = "communication"
                            if "(type: " in msg:
                                # Extract error type from enhanced error message
                                try:
                                    type_start = msg.find("(type: ") + 7
                                    type_end = msg.find(")", type_start)
                                    if type_end > type_start:
                                        error_type = msg[type_start:type_end]
                                except:
                                    pass
                            
                            # Get instrument info for detailed logging
                            instrument_info = self._get_instrument_info(port, address)
                            
                            # Log to error logger with appropriate error type
                            if error_type == "port_closed":
                                # Clear shared cache to force reconnection
                                self.clear_shared_instrument_cache(port, address)
                                self.error_logger.log_error(
                                    port=port,
                                    address=str(address),
                                    error_type="hardware",
                                    error_message="Serial port closed unexpectedly",
                                    error_details=msg,
                                    instrument_info=instrument_info
                                )
                            elif error_type == "timeout":
                                self.error_logger.log_communication_error(
                                    port=port,
                                    address=str(address),
                                    error_message="Communication timeout",
                                    instrument_info=instrument_info
                                )
                            elif error_type in ["permission_denied", "device_not_found"]:
                                self.error_logger.log_error(
                                    port=port,
                                    address=str(address),
                                    error_type="hardware",
                                    error_message=f"Port access error: {error_type}",
                                    error_details=msg,
                                    instrument_info=instrument_info
                                )
                            else:
                                # Default communication error
                                self.error_logger.log_communication_error(
                                    port=port,
                                    address=str(address),
                                    error_message=msg,
                                    instrument_info=instrument_info
                                )
                        except ValueError:
                            # Address part is not a valid integer
                            self.error_logger.log_error(
                                port=port_addr,
                                address="unknown",
                                error_type="communication",
                                error_message="Poller error (invalid address format)",
                                error_details=msg
                            )
                    else:
                        # Could not split properly
                        self.error_logger.log_error(
                            port=port_addr,
                            address="unknown",
                            error_type="communication",
                            error_message="Poller error (parse failed)",
                            error_details=msg
                        )
            else:
                # Generic error without specific port/address
                self.error_logger.log_error(
                    port="unknown",
                    address="unknown", 
                    error_type="communication",
                    error_message="Poller error",
                    error_details=msg
                )
        except Exception as e:
            # If parsing fails, still log the error
            print(f"Error parsing poller error message: {e}")
            self.error_logger.log_error(
                port="unknown",
                address="unknown",
                error_type="communication", 
                error_message="Poller error (parse failed)",
                error_details=msg
            )

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

    # ---- Gas Factor Management with Persistent Storage ----
    def _load_gas_factors(self):
        """Load gas factors from JSON file"""
        try:
            if os.path.exists(self._gas_factors_file):
                with open(self._gas_factors_file, 'r') as f:
                    self._persistent_gas_factors = json.load(f)
            else:
                self._persistent_gas_factors = {}
        except Exception as e:
            print(f"⚠️  Error loading gas factors: {e}")
            self._persistent_gas_factors = {}

    def _save_gas_factors(self):
        """Save gas factors to JSON file"""
        try:
            with open(self._gas_factors_file, 'w') as f:
                json.dump(self._persistent_gas_factors, f, indent=2)
        except Exception as e:
            print(f"⚠️  Error saving gas factors: {e}")

    def set_gas_factor(self, port: str, address: int, factor: float, serial_nr: str = None):
        """Set gas compensation factor for a specific instrument"""
        # Store in temporary memory (by port/address)
        self._gas_factors[(port, address)] = factor
        
        # Store persistently by serial number if available
        if serial_nr:
            self._persistent_gas_factors[str(serial_nr)] = factor
            self._save_gas_factors()

    def get_gas_factor(self, port: str, address: int, serial_nr: str = None) -> float:
        """Get gas compensation factor for a specific instrument (default: 1.0)"""
        # First try to get from persistent storage by serial number
        if serial_nr and str(serial_nr) in self._persistent_gas_factors:
            factor = self._persistent_gas_factors[str(serial_nr)]
            # Also update the temporary cache
            self._gas_factors[(port, address)] = factor
            return factor
        
        # Fallback to temporary storage by port/address
        return self._gas_factors.get((port, address), 1.0)

    def clear_gas_factor(self, port: str, address: int, serial_nr: str = None):
        """Clear gas compensation factor for a specific instrument"""
        # Clear from temporary storage
        key = (port, address)
        if key in self._gas_factors:
            del self._gas_factors[key]
        
        # Clear from persistent storage if serial number provided
        if serial_nr and str(serial_nr) in self._persistent_gas_factors:
            del self._persistent_gas_factors[str(serial_nr)]
            self._save_gas_factors()

    def get_all_gas_factors(self) -> Dict[str, float]:
        """Get all persistent gas factors by serial number"""
        return self._persistent_gas_factors.copy()

    def get_serial_number(self, port: str, address: int) -> Optional[str]:
        """Get serial number for a specific instrument"""
        for node in self._nodes:
            if node.port == port and node.address == address:
                return node.serial
        return None

    def get_device_type(self, port: str, address: int) -> Optional[str]:
        """Get device type for a specific instrument"""
        for node in self._nodes:
            if node.port == port and node.address == address:
                return node.dev_type
        return None

    # ---- Optional: port-wide lock for legacy I/O ----
    @contextmanager
    def port_lock(self, port: str):
        lock = self._port_locks.setdefault(port, threading.RLock())
        lock.acquire()
        try:
            yield
        finally:
            lock.release()