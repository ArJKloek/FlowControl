# propar_qt/scanner.py
import glob
from typing import List, Optional

from PyQt5.QtCore import QThread, pyqtSignal, QObject
import serial
from propar_new import master as ProparMaster # your uploaded lib
#from propar import instrument as ProparInstrument  
from .types import NodeInfo
from collections.abc import Iterable
import time



def _read_dde_stable(master, address, ddes, attempts=5, delay=0.15, debug=False):
    """
    Enhanced robust multi-read:
    - does a chained read,
    - retries only the DDEs that came back bad/None,
    - strips trailing spaces for strings.
    - increased attempts and delay for better reliability.
    - optional debug output for troubleshooting.
    Returns {dde: value or None}.
    """
    if isinstance(ddes, int):
        ddes = [ddes]
    ddes = [int(d) for d in ddes]

    data = {d: None for d in ddes}
    bad  = set(ddes)

    if debug:
        print(f"Reading DDEs {ddes} from address {address}")

    for k in range(max(1, int(attempts))):
        if k > 0:
            time.sleep(delay)

        # read only the still-bad ones
        params = []
        for d in list(bad):
            try:
                p = master.db.get_parameter(d)
                p['node'] = address
                params.append(p)
            except Exception as e:
                # If parameter lookup fails, mark as permanently bad
                if debug:
                    print(f"Parameter lookup failed for DDE {d}: {e}")
                bad.discard(d)
                continue

        if not params:
            break

        try:
            res = master.read_parameters(params) or []
            for p, r in zip(params, res):
                d = p['dde_nr']
                if r and r.get('status', 1) == 0 and r.get('data', None) is not None:
                    v = r['data']
                    if isinstance(v, str):
                        v = v.strip()
                    elif isinstance(v, bytes):
                        try:
                            v = v.decode('utf-8', errors='ignore').strip()
                        except:
                            pass
                    data[d] = v
                    bad.discard(d)
                    if debug:
                        print(f"Successfully read DDE {d}: {v}")
                elif debug:
                    status = r.get('status', 'unknown') if r else 'no response'
                    print(f"Failed to read DDE {d}: status={status}")
                # else: keep in bad for another pass
        except Exception as e:
            if debug:
                print(f"Communication error on attempt {k+1}: {e}")
            # Communication error - wait longer before next attempt
            if k < attempts - 1:
                time.sleep(delay * 2)

    if debug and bad:
        print(f"Final failed DDEs for address {address}: {list(bad)}")

    return data
    
def _write_dde_ok(master, address, dde, value):
    """
    Normalize write success across different return shapes.
    Returns True iff clearly successful.
    """
    try:
        p = master.db.get_parameter(int(dde))
        p['node'] = address
        p['data'] = value
        st = master.write_parameters([p])  # WITH_ACK by default
    except Exception:
        return False

    # True / 0 / dict status 0 / list of OKs
    if st is True or st == 0:
        return True
    if isinstance(st, dict):
        return st.get('status', 1) == 0
    if isinstance(st, (list, tuple)):
        for x in st:
            if isinstance(x, dict):
                if x.get('status', 1) != 0:
                    return False
            elif isinstance(x, int):
                if x != 0:
                    return False
            else:
                return False
        return True
    return False
   
def _apply_fluid_and_get_name(master, address, idx, settle_timeout=5.0):
    """
    Write DDE 24 = idx, then wait until 24==idx and 25 (name) is non-empty.
    Returns the fluid name (str) or None if it didn’t settle in time.
    """
    ok = _write_dde_ok(master, address, 24, int(idx))
    # Even if the write 'times out', many devices still apply it.
    # Verify by reading back 24/25 until consistent.
    deadline = time.time() + float(settle_timeout)
    name = None
    while time.time() < deadline:
        vals = _read_dde_stable(master, address, [24, 25], attempts=1)
        if vals.get(24) == int(idx):
            nm = vals.get(25)
            if nm:
                name = nm
                break
        time.sleep(0.15)
    return name


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
                    # Assign a number to each instrument
                    numbered_info = {
                        "number": instrument_counter,
                        "info": info
                    }
                    info.number = instrument_counter  # Add number attribute to NodeInfo

                    # Always load instrument - wrap parameter reading in try-except for robustness
                    try:
                        vals = _read_dde_stable(m, info.address, [115, 25, 21, 129, 24, 206, 91, 175], debug=True)
                        info.usertag, info.fluid, info.capacity, info.unit, orig_idx, info.fsetpoint, info.model = (
                            vals.get(115), vals.get(25), vals.get(21), vals.get(129), vals.get(24), vals.get(206), vals.get(91)  
                        )
                        
                        # Add device type detection using parameter 175
                        device_type_id = vals.get(175)
                    except Exception as param_error:
                        # If parameter reading fails completely, use default values
                        print(f"Warning: Parameter reading failed for instrument {info.address}: {param_error}")
                        print(f"         Loading instrument with default values for control purposes")
                        
                        vals = {}  # Empty dict for consistent code below
                        info.usertag = f"Instrument_{info.address}"
                        info.fluid = "Unknown"
                        info.capacity = 100.0  # Default capacity
                        info.unit = "ml/min"  # Default unit
                        orig_idx = 0  # Default fluid index
                        info.fsetpoint = 0.0  # Default setpoint
                        info.model = f"Unknown_Model_Addr{info.address}"
                        device_type_id = None  # Unknown device type
                    if device_type_id is not None:
                        device_types = {
                            7: "DMFC", 8: "DMFM", 9: "DEPC", 10: "DEPM", 
                            12: "DLFC", 13: "DLFM"
                        }
                        info.device_type = device_types.get(device_type_id, f"Unknown({device_type_id})")
                    else:
                        info.device_type = "Unknown"
                    
                    # Check for missing parameters but always load the instrument
                    missing_params = []
                    if info.capacity is None:
                        missing_params.append("capacity(21)")
                    if info.unit is None:
                        missing_params.append("unit(129)")
                    if info.model is None:
                        missing_params.append("model(91)")
                    
                    # Always load instruments - prefer control availability over complete parameter data
                    if missing_params:
                        # Log warning but always continue - user wants instrument control
                        print(f"Warning: Some parameters missing for instrument {info.address}: {', '.join(missing_params)}")
                        print(f"         Instrument will still be loaded for control purposes")
                        
                        # Set default values for missing critical parameters to ensure UI compatibility
                        if info.model is None:
                            info.model = f"Unknown_Model_Addr{info.address}"
                        if info.capacity is None:
                            info.capacity = 100.0  # Default capacity
                        if info.unit is None:
                            info.unit = "ml/min"  # Default unit
                    
                    # Debug logging for successful parameter reads
                    print(f"Instrument {info.address}: capacity={info.capacity}, unit={info.unit}, model={info.model}, device_type={info.device_type}")
                    rows = []
                    try:
                        # Add timeout protection for fluid table scanning
                        scan_start_time = time.time()
                        max_scan_time = 25.0  # 25 second timeout for complete fluid scan
                        
                        for idx in range(0, 8):
                            if self._stop:
                                break
                                
                            # Check for timeout
                            if time.time() - scan_start_time > max_scan_time:
                                self.portError.emit(port, f"Fluid scan timeout for instrument {info.address}")
                                break
                            
                            try:
                                name = _apply_fluid_and_get_name(m, info.address, idx, settle_timeout=1.0)
                                if name and name.strip():   # not None, empty, or whitespace-only
                                    rows.append({"index": idx, "name": name.strip()})
                            except Exception as e:
                                # Log individual fluid read failure but continue
                                continue
                           # if not self._write_dde(m, info.address, 24, idx):
                            #    continue

                            #vals = self._read_dde(m, info.address, [25]) 
                            #name= vals.get(25)

                            #if name not in (None, "", b""):
                            #    rows.append({
                            #        "index": idx,
                            #        "name": name,
                            #    })
                    finally:
                        if orig_idx is not None:
                            _write_dde_ok(m, info.address, 24, int(orig_idx))
                    
                    info.fluids_table = rows
                    self.instrument_list.append(numbered_info)
                    instrument_counter += 1
                    self.nodeFound.emit(info)
            except serial.SerialException as e:
                self.portError.emit(port, f"Serial communication error: {e}")
            except Exception as e:
                self.portError.emit(port, f"Unexpected scanning error: {str(e)[:100]}...")  # Truncate long error messages
        self.finishedScanning.emit()