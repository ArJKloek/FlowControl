# Enhanced USB Error Handling and Recovery

This document describes the enhanced error handling and recovery mechanisms implemented to address USB disconnection issues like "Bad file descriptor" errors.

## Problem Analysis

The original error logs showed:
```
2025-10-07T20:09:29.763684,/dev/ttyUSB0,6,SERIAL_CONNECTION_LOST,Serial file descriptor lost: write failed: [Errno 9] Bad file descriptor
2025-10-07T20:09:29.769509,unknown,unknown,communication,Poller error,Communication lost with device /dev/ttyUSB0 address 6. Serial connection dropped.
```

This indicates USB device disconnection or driver-level issues causing the serial port to become invalid.

## Enhanced Features Implemented

### 1. **Advanced Error Classification**

Enhanced error detection for USB-specific issues:

```python
usb_disconnect_indicators = [
    "bad file descriptor", "errno 9", "write failed", "read failed",
    "device disconnected", "device not found", "no such file or directory",
    "port that is not open", "serial exception", "connection lost"
]
```

**Error Types:**
- `bad_file_descriptor` - USB device disconnected
- `write_read_failed` - I/O operation failed
- `device_disconnected` - Physical disconnection
- `usb_disconnection` - General USB communication loss
- `port_closed` - Serial port closed unexpectedly
- `device_not_found` - Device no longer available

### 2. **Consecutive Error Tracking**

Prevents infinite retry loops by tracking consecutive failures:

```python
# Track errors per address
self._consecutive_errors = {}  # address -> error_count
self._last_error_time = {}     # address -> timestamp

# Temporary disable after 10 consecutive errors
if self._consecutive_errors[address] >= 10:
    # Remove from polling temporarily
    # Automatic re-enable after 60 seconds
```

**Features:**
- ✅ Tracks errors per address independently
- ✅ Resets error count after 30 seconds of no errors
- ✅ Temporarily disables problematic addresses
- ✅ Automatic re-enabling after recovery period
- ✅ Resets count on successful communication

### 3. **Variable Recovery Delays**

Different delay strategies based on error severity:

```python
# USB disconnections - longer delay for device recovery
if error_type in ["bad_file_descriptor", "write_read_failed", "device_disconnected"]:
    time.sleep(1.0)  # 1 second
# Port issues - medium delay
elif error_type in ["port_closed", "device_not_found"]:
    time.sleep(0.5)  # 500ms
# Timeouts - short delay
elif error_type == "timeout":
    time.sleep(0.1)  # 100ms
# Other errors - minimal delay
else:
    time.sleep(0.05)  # 50ms
```

### 4. **Enhanced Recovery Actions**

Comprehensive recovery for USB disconnections:

```python
if should_clear_cache:
    # Clear instrument cache to force reconnection
    self.manager.clear_shared_instrument_cache(self.port, address)
    # Clear parameter cache for fresh lookup
    if address in self._param_cache:
        del self._param_cache[address]

if should_reconnect:
    # Force port reconnection
    self.manager.force_reconnect_port(self.port)
```

**Recovery Steps:**
1. **Clear cached instruments** - Forces new connection
2. **Clear parameter cache** - Fresh parameter lookup
3. **Force port reconnection** - Recreates master connection
4. **Emit specific error signals** - Better error reporting

### 5. **Improved Error Logging**

Enhanced logging with more context:

```python
if hasattr(self.manager, 'error_logger') and self.manager.error_logger:
    self.manager.error_logger.log_error(
        port=self.port,
        address=str(address),
        error_type="SERIAL_CONNECTION_LOST",
        error_message=f"Serial file descriptor lost: {error_msg}",
        error_details=f"Error type: {error_type}, Port: {self.port}, Address: {address}"
    )
```

## Manager-Level Enhancements

### Enhanced Address Validation

```python
def get_shared_instrument(self, port: str, address: int, channel: int = 1):
    # Validate address format
    try:
        address = int(address)
        if not (1 <= address <= 247):
            raise ValueError(f"Address {address} out of valid range (1-247)")
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid address format '{address}': {e}")
```

### Robust Recovery Methods

```python
def force_reconnect_port(self, port: str):
    """Force reconnection by clearing cache and recreating master."""
    with self.port_lock(port):
        # Clear all cached instruments
        if port in self._shared_inst_cache:
            self._shared_inst_cache[port].clear()
        
        # Close and recreate master connection
        if port in self._masters:
            try:
                old_master = self._masters[port]
                if hasattr(old_master, 'close'):
                    old_master.close()
            except Exception:
                pass
            
            # Create new master
            self._masters[port] = ProparMaster(port, baudrate=self._baudrate)
```

## Benefits

### **Reliability Improvements:**
- ✅ **Automatic recovery** from USB disconnections
- ✅ **Prevents infinite retry loops** with consecutive error tracking
- ✅ **Self-healing** system that re-enables recovered devices
- ✅ **Graceful degradation** when devices fail

### **Performance Optimizations:**
- ✅ **Variable delays** prevent unnecessary waiting
- ✅ **Cache clearing** ensures fresh connections
- ✅ **Error count reset** on successful communication
- ✅ **Temporary disabling** prevents resource waste

### **Debugging & Monitoring:**
- ✅ **Enhanced error classification** for better diagnosis
- ✅ **Detailed logging** with error context
- ✅ **Status reporting** for error recovery progress
- ✅ **Error count tracking** for reliability metrics

## Usage

The enhanced error handling is automatic and backward compatible:

```python
# Existing code continues to work unchanged
poller = PortPoller(manager, "/dev/ttyUSB0", addresses=[1, 2, 3])

# Enhanced features work automatically:
# - USB disconnection detection
# - Automatic recovery attempts
# - Consecutive error tracking
# - Variable recovery delays
# - Cache clearing and reconnection
```

## Testing

Run the test suite to verify functionality:

```bash
python test_usb_error_handling.py
```

**Test Coverage:**
- ✅ Error classification accuracy
- ✅ Consecutive error tracking
- ✅ Automatic re-enabling
- ✅ Recovery delay timing
- ✅ Error count reset on success

## Expected Results

With these enhancements, USB disconnection errors should:

1. **Be properly classified** and handled with appropriate recovery
2. **Trigger automatic cache clearing** and reconnection attempts
3. **Temporarily disable** problematic addresses to prevent resource waste
4. **Automatically re-enable** devices after recovery period
5. **Provide detailed logging** for debugging and monitoring
6. **Reset error counts** when communication is restored

The system should now be much more resilient to USB device disconnections and provide better recovery mechanisms for the "Bad file descriptor" errors you were experiencing.