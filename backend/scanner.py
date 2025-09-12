# propar_qt/scanner.py
import glob
from typing import List, Optional

from PyQt5.QtCore import QThread, pyqtSignal, QObject
import serial
import propar
from propar import master as ProparMaster # your uploaded lib
#from propar import instrument as ProparInstrument  
from .types import NodeInfo
from collections.abc import Iterable

def _default_ports() -> List[str]:
    """Return common serial device paths on Raspberry Pi/Linux.
    Includes USB CDC ACM, USB serial, and the onboard UART symlinks.
    """
    patterns = [
        '/dev/ttyUSB*', # USB-serial adapters
        #'/dev/ttyACM*', # CDC ACM devices (many dev boards)
        #'/dev/serial0', # primary UART symlink on Pi
        #'/dev/ttyAMA0', # PL011 UART (older/newer Pi variants)
    ]
    found = []
    for pat in patterns:
        found.extend(glob.glob(pat))
    # de-duplicate while preserving order
    seen = set()
    ordered = []
    for f in found:
        if f not in seen:
            ordered.append(f)
            seen.add(f)
    return ordered

class ProparScanner(QThread):
    """
    Scans ports for Propar nodes without blocking the UI.
    Emits:
    - nodeFound(NodeInfo)
    - portError(str, str)
    - startedPort(str)
    - finishedScanning()
    """
    nodeFound = pyqtSignal(object)
    portError = pyqtSignal(str, str)
    startedPort = pyqtSignal(str)
    finishedScanning = pyqtSignal()


    def __init__(self, ports: Optional[List[str]] = None, baudrate: int = 38400, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._ports = ports or _default_ports()
        self._baudrate = baudrate
        self._stop = False
        self.instrument_list = []  # Store instruments with numbers


    def stop(self):
        self._stop = True

    @staticmethod
    def _read_dde(master, address, dde_or_list):
        """
        Read one or many DDE parameters.
        - If `dde_or_list` is an int: returns the single value or None.
        - If it's an iterable of ints: returns {dde: value_or_None} using a chained read.
        """
        try:
            # ---- multiple DDEs (chained read) ----
            if isinstance(dde_or_list, Iterable) and not isinstance(dde_or_list, (str, bytes)):
                ddes = [int(d) for d in dde_or_list]
                params = []
                for d in ddes:
                    p = master.db.get_parameter(d)
                    p['node'] = address
                    params.append(p)
                res = master.read_parameters(params)  # list of dicts, same order as params
                out = {}
                for d, r in zip(ddes, res or []):
                    out[d] = r.get('data') if r and r.get('status', 1) == 0 else None
                return out

            # ---- single DDE ----
            d = int(dde_or_list)
            p = master.db.get_parameter(d)
            p['node'] = address
            res = master.read_parameters([p])
            if res and res[0].get('status', 1) == 0:
                return res[0]['data']
            return None

        except Exception:
            return None

    @staticmethod
    def _write_dde(master, address, dde, value):
        try:
            p = master.db.get_parameter(dde); p['node'] = address; p['data'] = value
            status = master.write_parameters([p])                  # default is WITH_ACK
            return status == 0
        except Exception:
            return False
        

    def run(self):
        instrument_counter = 1
        for port in list(self._ports):
            if self._stop:
                break
            self.startedPort.emit(port)                 # <-- emit start for this port
            try:
                m = ProparMaster(port, baudrate=self._baudrate)
                nodes = m.get_nodes()
                for n in nodes:
                    if self._stop:
                        break
                    info = NodeInfo(
                        port=port,
                        address=int(n['address']),
                        dev_type=str(n['type']),
                        serial=str(n['serial']),
                        id_str=str(n['id']),
                        channels=int(n['channels'])
                    )
                    print(f"Found: {info}")  # <-- debug print
                    # Assign a number to each instrument
                    numbered_info = {
                        "number": instrument_counter,
                        "info": info
                    }
                    info.number = instrument_counter  # Add number attribute to NodeInfo

                    vals = self._read_dde(m, info.address, [115, 25, 21, 129, 24])
                    info.usertag, info.fluid, info.capacity, info.unit, orig_idx = (
                        vals.get(115), vals.get(25), vals.get(21), vals.get(129), vals.get(24)    
                    )
                    rows = []
                    try:
                        for idx in range(0, 8):
                            if not self._write_dde(m, info.address, 24, idx):
                                continue

                            vals = self._read_dde(m, info.address, [25]) 
                            name= vals.get(25)

                            if name not in (None, "", b""):
                                rows.append({
                                    "index": idx,
                                    "name": name,
                                })
                    finally:
                        if orig_idx is not None:
                            self._write_dde(m, info.address, 24, int(orig_idx))
                    
                    info.fluids_table = rows
                    self.instrument_list.append(numbered_info)
                    instrument_counter += 1
                    self.nodeFound.emit(info)
            except serial.SerialException as e:
                self.portError.emit(port, f"Serial error: {e}")
            except Exception as e:
                self.portError.emit(port, f"Error: {e}")
        self.finishedScanning.emit()