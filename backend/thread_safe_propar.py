#!/usr/bin/env python3
"""
Thread-Safe Serial Port Wrapper for Bronkhorst Propar Communication

This module provides a thread-safe wrapper around the Propar Master class to ensure
that only one instrument query is processed at a time on each serial port. This prevents
USB communication crashes caused by concurrent access to the same USB-to-RS485 adapter.

Key Features:
- Serializes all read/write operations on a per-port basis
- Prevents "Bad file descriptor" errors from concurrent access
- Maintains compatibility with existing Propar API
- Provides automatic retry and error recovery
- Includes comprehensive logging and statistics
"""

import threading
import time
import queue
import struct
from typing import Dict, Any, Optional, Callable
from contextlib import contextmanager
import logging

# Set up logging
logger = logging.getLogger(__name__)


class SerialPortManager:
    """
    Thread-safe manager for serial port access.
    
    Ensures only one operation at a time per port, preventing USB communication conflicts.
    """
    
    def __init__(self):
        self._port_locks: Dict[str, threading.RLock] = {}
        self._port_stats: Dict[str, dict] = {}
        self._global_lock = threading.RLock()
        
    def get_port_lock(self, port: str) -> threading.RLock:
        """Get or create a thread lock for the specified port."""
        with self._global_lock:
            if port not in self._port_locks:
                self._port_locks[port] = threading.RLock()
                self._port_stats[port] = {
                    'total_operations': 0,
                    'successful_operations': 0,
                    'failed_operations': 0,
                    'last_operation_time': None,
                    'longest_operation_ms': 0,
                    'concurrent_attempts_blocked': 0
                }
            return self._port_locks[port]
    
    @contextmanager
    def acquire_port(self, port: str):
        """Context manager for acquiring exclusive access to a port."""
        port_lock = self.get_port_lock(port)
        operation_start = time.time()
        
        # Check if another thread is already using this port
        if not port_lock.acquire(blocking=False):
            self._port_stats[port]['concurrent_attempts_blocked'] += 1
            logger.debug(f"🔒 Port {port} busy, waiting for access...")
            port_lock.acquire()  # Block until available
        
        try:
            self._port_stats[port]['total_operations'] += 1
            self._port_stats[port]['last_operation_time'] = time.time()
            logger.debug(f"🔓 Acquired exclusive access to port {port}")
            yield
            
            # Track successful operation
            operation_time_ms = (time.time() - operation_start) * 1000
            self._port_stats[port]['successful_operations'] += 1
            if operation_time_ms > self._port_stats[port]['longest_operation_ms']:
                self._port_stats[port]['longest_operation_ms'] = operation_time_ms
                
        except Exception as e:
            self._port_stats[port]['failed_operations'] += 1
            logger.error(f"❌ Operation failed on port {port}: {e}")
            raise
        finally:
            port_lock.release()
            logger.debug(f"🔓 Released exclusive access to port {port}")
    
    def get_port_statistics(self, port: str) -> dict:
        """Get statistics for a specific port."""
        return self._port_stats.get(port, {}).copy()
    
    def get_all_statistics(self) -> dict:
        """Get statistics for all ports."""
        return {port: stats.copy() for port, stats in self._port_stats.items()}


# Global instance for the application
_serial_port_manager = SerialPortManager()


class ThreadSafeProparMaster:
    """
    Thread-safe wrapper around Propar Master that serializes all operations.
    
    This class ensures that only one read/write operation occurs at a time on each
    serial port, preventing USB communication conflicts and crashes.
    """
    
    def __init__(self, comport: str, baudrate: int = 38400, serial_class=None):
        """
        Initialize thread-safe Propar master.
        
        Args:
            comport: Serial port (e.g., 'COM1', '/dev/ttyUSB0')
            baudrate: Communication baud rate
            serial_class: Custom serial class (optional)
        """
        self.comport = comport
        self.baudrate = baudrate
        self.serial_class = serial_class
        self._master = None
        self._master_lock = threading.RLock()
        self._create_master()
        
        logger.info(f"🔧 Created ThreadSafeProparMaster for {comport} @ {baudrate} baud")
    
    def _create_master(self):
        """Create or recreate the underlying Propar master."""
        try:
            import propar
            if self.serial_class:
                self._master = propar.master(self.comport, self.baudrate, self.serial_class)
            else:
                self._master = propar.master(self.comport, self.baudrate)
            logger.debug(f"✅ Created Propar master for {self.comport}")
        except Exception as e:
            logger.error(f"❌ Failed to create Propar master for {self.comport}: {e}")
            raise
    
    def _execute_with_retry(self, operation: Callable, operation_name: str, max_retries: int = 2):
        """
        Execute an operation with retry logic and proper error handling.
        
        Args:
            operation: Function to execute
            operation_name: Name of operation for logging
            max_retries: Maximum number of retry attempts
            
        Returns:
            Result of the operation
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                with _serial_port_manager.acquire_port(self.comport):
                    if attempt > 0:
                        logger.info(f"🔄 Retry {attempt}/{max_retries} for {operation_name} on {self.comport}")
                    
                    result = operation()
                    
                    if attempt > 0:
                        logger.info(f"✅ {operation_name} succeeded on retry {attempt}")
                    
                    return result
                    
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()
                
                # Check for known USB/serial errors and Propar protocol errors that might be recoverable
                if any(error_pattern in error_msg for error_pattern in [
                    'bad file descriptor', 'device not configured', 'no such device',
                    'resource temporarily unavailable', 'connection aborted',
                    'list index out of range', 'index out of range',  # Propar message parsing errors
                    'message handler', 'parameter message',  # Propar protocol errors
                    'unpack requires', 'struct.error'  # Message format errors
                ]):
                    logger.warning(f"⚠️  USB/Serial error in {operation_name} on {self.comport} (attempt {attempt + 1}): {e}")
                    
                    if attempt < max_retries:
                        # Try to recreate the master for USB errors
                        try:
                            logger.info(f"🔧 Recreating master for {self.comport} due to USB error")
                            with self._master_lock:
                                self._create_master()
                            # � EXTENDED retry delay: More time for slow instruments
                            time.sleep(0.1 * (attempt + 1))  # Was 0.02s, now 0.1s (5x longer for reliability)
                        except Exception as recreate_error:
                            logger.error(f"❌ Failed to recreate master: {recreate_error}")
                    continue
                else:
                    # Non-recoverable error, don't retry
                    logger.error(f"❌ Non-recoverable error in {operation_name} on {self.comport}: {e}")
                    break
        
        # All retries failed
        logger.error(f"❌ {operation_name} failed after {max_retries + 1} attempts on {self.comport}")
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError(f"{operation_name} failed after all retry attempts")
    
    def read(self, address: int, proc_nr: int, parm_nr: int, parm_type: int):
        """Thread-safe read operation with enhanced Propar error handling."""
        def _read():
            with self._master_lock:
                try:
                    return self._master.read(address, proc_nr, parm_nr, parm_type)
                except IndexError as e:
                    # Handle Propar message parsing errors specifically
                    if "list index out of range" in str(e):
                        logger.warning(f"🔧 Propar message parsing error on {self.comport}: {e}")
                        raise RuntimeError(f"Propar message parsing failed: {e}")
                    raise
                except (struct.error, ValueError) as e:
                    # Handle message format errors
                    logger.warning(f"🔧 Propar message format error on {self.comport}: {e}")
                    raise RuntimeError(f"Propar message format error: {e}")
        
        return self._execute_with_retry(
            _read, 
            f"read(addr={address}, proc={proc_nr}, parm={parm_nr})",
            max_retries=3  # More retries for Propar errors
        )
    
    def write(self, address: int, proc_nr: int, parm_nr: int, parm_type: int, data):
        """Thread-safe write operation with enhanced Propar error handling."""
        def _write():
            with self._master_lock:
                try:
                    return self._master.write(address, proc_nr, parm_nr, parm_type, data)
                except IndexError as e:
                    # Handle Propar message parsing errors specifically
                    if "list index out of range" in str(e):
                        logger.warning(f"🔧 Propar message parsing error on {self.comport}: {e}")
                        raise RuntimeError(f"Propar message parsing failed: {e}")
                    raise
                except (struct.error, ValueError) as e:
                    # Handle message format errors
                    logger.warning(f"🔧 Propar message format error on {self.comport}: {e}")
                    raise RuntimeError(f"Propar message format error: {e}")
        
        return self._execute_with_retry(
            _write,
            f"write(addr={address}, proc={proc_nr}, parm={parm_nr}, data={data})",
            max_retries=3  # More retries for Propar errors
        )
    
    def read_parameters(self, parameters: list, callback=None):
        """Thread-safe read multiple parameters with enhanced Propar error handling."""
        def _read_params():
            with self._master_lock:
                try:
                    return self._master.read_parameters(parameters, callback)
                except IndexError as e:
                    # Handle Propar message parsing errors specifically
                    if "list index out of range" in str(e):
                        logger.warning(f"🔧 Propar bulk read parsing error on {self.comport}: {e}")
                        raise RuntimeError(f"Propar bulk read parsing failed: {e}")
                    raise
                except (struct.error, ValueError) as e:
                    # Handle message format errors
                    logger.warning(f"🔧 Propar bulk read format error on {self.comport}: {e}")
                    raise RuntimeError(f"Propar bulk read format error: {e}")
        
        return self._execute_with_retry(
            _read_params,
            f"read_parameters({len(parameters)} params)",
            max_retries=3  # More retries for Propar errors
        )
    
    def write_parameters(self, parameters: list, command: int = 1, callback=None):
        """Thread-safe write multiple parameters with enhanced Propar error handling."""
        def _write_params():
            with self._master_lock:
                try:
                    return self._master.write_parameters(parameters, command, callback)
                except IndexError as e:
                    # Handle Propar message parsing errors specifically
                    if "list index out of range" in str(e):
                        logger.warning(f"🔧 Propar bulk write parsing error on {self.comport}: {e}")
                        raise RuntimeError(f"Propar bulk write parsing failed: {e}")
                    raise
                except (struct.error, ValueError) as e:
                    # Handle message format errors
                    logger.warning(f"🔧 Propar bulk write format error on {self.comport}: {e}")
                    raise RuntimeError(f"Propar bulk write format error: {e}")
        
        return self._execute_with_retry(
            _write_params,
            f"write_parameters({len(parameters)} params)",
            max_retries=3  # More retries for Propar errors
        )
    
    def get_nodes(self, find_first: bool = True):
        """Thread-safe get nodes operation."""
        def _get_nodes():
            with self._master_lock:
                return self._master.get_nodes(find_first)
        
        return self._execute_with_retry(
            _get_nodes,
            "get_nodes"
        )
    
    def start(self):
        """Thread-safe start operation."""
        def _start():
            with self._master_lock:
                return self._master.start()
        
        return self._execute_with_retry(_start, "start")
    
    def stop(self):
        """Thread-safe stop operation."""
        def _stop():
            with self._master_lock:
                return self._master.stop()
        
        return self._execute_with_retry(_stop, "stop")
    
    def set_baudrate(self, baudrate: int):
        """Thread-safe set baudrate operation."""
        def _set_baudrate():
            with self._master_lock:
                self.baudrate = baudrate
                return self._master.set_baudrate(baudrate)
        
        return self._execute_with_retry(_set_baudrate, f"set_baudrate({baudrate})")
    
    def dump(self, level: int = 1):
        """Thread-safe dump operation."""
        with self._master_lock:
            return self._master.dump(level)
    
    @property
    def db(self):
        """Access to the database (thread-safe)."""
        with self._master_lock:
            return self._master.db
    
    def get_statistics(self) -> dict:
        """Get port statistics for this master."""
        return _serial_port_manager.get_port_statistics(self.comport)


class ThreadSafeProparInstrument:
    """
    Thread-safe wrapper around Propar Instrument that uses ThreadSafeProparMaster.
    
    This ensures that all instrument operations are serialized on a per-port basis.
    """
    
    def __init__(self, comport: str, address: int = 128, baudrate: int = 38400, 
                 channel: int = 1, serial_class=None):
        """
        Initialize thread-safe Propar instrument.
        
        Args:
            comport: Serial port (e.g., 'COM1', '/dev/ttyUSB0')
            address: Instrument address (1-247)
            baudrate: Communication baud rate
            channel: Instrument channel
            serial_class: Custom serial class (optional)
        """
        self.comport = comport
        self.address = address
        self.baudrate = baudrate
        self.channel = channel
        
        # Use thread-safe master
        self.master = ThreadSafeProparMaster(comport, baudrate, serial_class)
        
        logger.info(f"🔧 Created ThreadSafeProparInstrument for {comport}/addr:{address}/ch:{channel}")
    
    def readParameter(self, dde_nr: int, channel: Optional[int] = None):
        """Thread-safe read parameter by DDE number with enhanced error handling."""
        try:
            # Convert DDE number to propar parameters using database
            param = self.master.db.get_parameter(dde_nr)
            if not param:
                raise ValueError(f"Unknown DDE parameter number: {dde_nr}")
            
            use_channel = channel if channel is not None else self.channel
            return self.master.read(self.address, param['proc_nr'], param['parm_nr'], param['parm_type'])
        
        except IndexError as e:
            # Handle Propar message parsing errors specifically
            if "list index out of range" in str(e):
                logger.warning(f"🔧 Propar parameter read parsing error for DDE {dde_nr} on address {self.address}: {e}")
                raise RuntimeError(f"Propar parameter read parsing failed: {e}")
            raise
        except (struct.error, ValueError) as e:
            # Handle message format errors (except our own ValueError for unknown DDE)
            if "Unknown DDE parameter number" in str(e):
                raise  # Re-raise our own ValueError
            logger.warning(f"🔧 Propar parameter read format error for DDE {dde_nr} on address {self.address}: {e}")
            raise RuntimeError(f"Propar parameter read format error: {e}")
    
    def writeParameter(self, dde_nr: int, data, channel: Optional[int] = None, verify: bool = False, debug: bool = False):
        """Thread-safe write parameter by DDE number with enhanced error handling."""
        try:
            # Convert DDE number to propar parameters using database
            param = self.master.db.get_parameter(dde_nr)
            if not param:
                raise ValueError(f"Unknown DDE parameter number: {dde_nr}")
            
            use_channel = channel if channel is not None else self.channel
            result = self.master.write(self.address, param['proc_nr'], param['parm_nr'], param['parm_type'], data)
            
            if verify and result:
                # Verify the write by reading back
                try:
                    readback = self.readParameter(dde_nr, channel)
                    if readback != data:
                        logger.warning(f"⚠️  Write verification failed: wrote {data}, read {readback}")
                        return False
                except Exception as e:
                    logger.warning(f"⚠️  Write verification error: {e}")
            
            return result
        
        except IndexError as e:
            # Handle Propar message parsing errors specifically
            if "list index out of range" in str(e):
                logger.warning(f"🔧 Propar parameter write parsing error for DDE {dde_nr} on address {self.address}: {e}")
                raise RuntimeError(f"Propar parameter write parsing failed: {e}")
            raise
        except (struct.error, ValueError) as e:
            # Handle message format errors (except our own ValueError for unknown DDE)
            if "Unknown DDE parameter number" in str(e):
                raise  # Re-raise our own ValueError
            logger.warning(f"🔧 Propar parameter write format error for DDE {dde_nr} on address {self.address}: {e}")
            raise RuntimeError(f"Propar parameter write format error: {e}")
    
    def read_parameters(self, parameters: list, callback=None, channel: Optional[int] = None):
        """
        Thread-safe read multiple parameters.
        Ensures each parameter has the required 'node' field set to this instrument's address.
        """
        # Ensure all parameters have the 'node' field set to this instrument's address
        fixed_parameters = []
        for i, param in enumerate(parameters):
            if isinstance(param, dict):
                # Create a copy to avoid modifying the original
                fixed_param = param.copy()
                # Ensure 'node' field is set to this instrument's address
                fixed_param['node'] = self.address
                fixed_parameters.append(fixed_param)
            else:
                # If it's not a dict, pass it through (shouldn't happen but be safe)
                logger.warning(f"⚠️  Parameter {i} is not a dict: {type(param)} = {param}")
                fixed_parameters.append(param)
        
        return self.master.read_parameters(fixed_parameters, callback)
    
    def write_parameters(self, parameters: list, command: int = 1, callback=None, channel: Optional[int] = None):
        """
        Thread-safe write multiple parameters.
        Ensures each parameter has the required 'node' field set to this instrument's address.
        """
        # Ensure all parameters have the 'node' field set to this instrument's address
        fixed_parameters = []
        for param in parameters:
            if isinstance(param, dict):
                # Create a copy to avoid modifying the original
                fixed_param = param.copy()
                # Ensure 'node' field is set to this instrument's address
                fixed_param['node'] = self.address
                fixed_parameters.append(fixed_param)
            else:
                # If it's not a dict, pass it through (shouldn't happen but be safe)
                fixed_parameters.append(param)
        
        return self.master.write_parameters(fixed_parameters, command, callback)
    
    def read(self, proc_nr: int, parm_nr: int, parm_type: int):
        """Thread-safe read single parameter."""
        return self.master.read(self.address, proc_nr, parm_nr, parm_type)
    
    def write(self, proc_nr: int, parm_nr: int, parm_type: int, data):
        """Thread-safe write single parameter."""
        return self.master.write(self.address, proc_nr, parm_nr, parm_type, data)
    
    def wink(self, time: int = 9):
        """Thread-safe wink operation."""
        # Wink is typically DDE parameter 23
        return self.writeParameter(23, time)
    
    @property
    def setpoint(self):
        """Thread-safe setpoint property (0-32000 = 0-100%)."""
        return self.readParameter(9)  # DDE 9 = setpoint
    
    @setpoint.setter
    def setpoint(self, value):
        """Thread-safe setpoint setter."""
        self.writeParameter(9, value)
    
    @property
    def measure(self):
        """Thread-safe measure property (0-32000 = 0-100%)."""
        return self.readParameter(8)  # DDE 8 = measure
    
    @property
    def id(self):
        """Thread-safe ID property."""
        return self.readParameter(92)  # DDE 92 = ID
    
    @property
    def db(self):
        """Access to the database."""
        return self.master.db


def get_port_statistics() -> dict:
    """Get statistics for all serial ports."""
    return _serial_port_manager.get_all_statistics()


def print_port_statistics():
    """Print formatted statistics for all ports."""
    stats = get_port_statistics()
    
    if not stats:
        print("📊 No serial port activity recorded")
        return
    
    print("\n📊 SERIAL PORT STATISTICS")
    print("=" * 50)
    
    for port, port_stats in stats.items():
        print(f"\n🔌 Port: {port}")
        print(f"   📈 Total operations: {port_stats['total_operations']}")
        print(f"   ✅ Successful: {port_stats['successful_operations']}")
        print(f"   ❌ Failed: {port_stats['failed_operations']}")
        print(f"   🔒 Concurrent attempts blocked: {port_stats['concurrent_attempts_blocked']}")
        print(f"   ⏱️  Longest operation: {port_stats['longest_operation_ms']:.1f}ms")
        
        if port_stats['last_operation_time']:
            last_time = time.time() - port_stats['last_operation_time']
            print(f"   🕐 Last operation: {last_time:.1f}s ago")
        
        success_rate = 0
        if port_stats['total_operations'] > 0:
            success_rate = (port_stats['successful_operations'] / port_stats['total_operations']) * 100
        print(f"   📊 Success rate: {success_rate:.1f}%")


# Compatibility functions to replace the original propar functions
def instrument(comport: str, address: int = 128, baudrate: int = 38400, 
               channel: int = 1, serial_class=None) -> ThreadSafeProparInstrument:
    """Create a thread-safe Propar instrument."""
    return ThreadSafeProparInstrument(comport, address, baudrate, channel, serial_class)


def master(comport: str, baudrate: int = 38400, serial_class=None) -> ThreadSafeProparMaster:
    """Create a thread-safe Propar master."""
    return ThreadSafeProparMaster(comport, baudrate, serial_class)


if __name__ == "__main__":
    # Test the thread-safe wrapper
    print("🧪 Testing Thread-Safe Propar Wrapper")
    print("This would normally connect to actual hardware...")
    
    # Example of how to use it
    print("\n📋 Usage Example:")
    print("import thread_safe_propar as propar")
    print("instrument = propar.instrument('COM1', address=3)")
    print("measure = instrument.readParameter(205)  # Thread-safe read")
    print("instrument.writeParameter(206, 10.5)     # Thread-safe write")
    print("propar.print_port_statistics()           # View statistics")