# Serial Connection Lost Error Handling - Implementation Summary

## Problem Resolved

**Original Error:**
```
2025-10-07T20:28:13.741511,/dev/ttyUSB0,6,SERIAL_CONNECTION_LOST,Serial file descriptor lost: Serial connection lost - file descriptor is None or port is closed
2025-10-07T20:28:13.755902,unknown,unknown,communication,Poller error,Communication lost with device /dev/ttyUSB0 address 6. Serial connection dropped.
```

## Enhanced Error Detection

### 1. **Expanded USB Disconnection Indicators**

Added new patterns to catch more serial connection issues:

```python
usb_disconnect_indicators = [
    "bad file descriptor", "errno 9", "write failed", "read failed",
    "device disconnected", "device not found", "no such file or directory",
    "port that is not open", "serial exception", "connection lost",
    "file descriptor is none", "port is closed", "serial connection lost"  # NEW
]
```

### 2. **Enhanced Error Classification**

**Your specific error** is now properly classified:
- `"Serial connection lost - file descriptor is None or port is closed"` → **`port_closed`**
- **Recovery delay**: 0.5 seconds (medium severity)
- **Actions**: Cache clearing + reconnection

### 3. **Dual Detection Points**

Enhanced error handling in **two critical locations**:

#### A. **read_parameters Exception Handler** (Primary Detection)
```python
if ("integer is required (got type NoneType)" in error_msg or 
    "file descriptor" in error_msg or 
    "Serial connection lost" in error_msg or
    "port is closed" in error_msg or
    "file descriptor is None" in error_msg):
```

**Features:**
- ✅ **Consecutive error tracking** per address
- ✅ **Enhanced logging** with error count context
- ✅ **Immediate cache clearing** and reconnection
- ✅ **Temporary disabling** after 10 consecutive errors
- ✅ **Auto re-enabling** after 60-second recovery
- ✅ **Extended rescheduling** delay (+1 second for serial errors)

#### B. **Main Polling Loop Exception Handler** (Secondary Detection)
```python
elif ("port that is not open" in error_msg_lower or 
      "port is closed" in error_msg_lower or
      "file descriptor is none" in error_msg_lower):
    error_type = "port_closed"
elif "serial connection lost" in error_msg_lower or "connection lost" in error_msg_lower:
    error_type = "serial_connection_lost"
```

**Features:**
- ✅ **Error type classification** for proper handling
- ✅ **Variable recovery delays** based on severity
- ✅ **USB disconnection signals** for UI notification
- ✅ **Comprehensive logging** with error type context

## Test Results

### **Error Detection Accuracy:**
```
✓ 'Serial connection lost - file descriptor is None or port is closed' -> port_closed
✓ 'Serial file descriptor lost: write failed: [Errno 9] Bad file descriptor' -> bad_file_descriptor
✓ 'file descriptor is None' -> port_closed
✓ 'port is closed' -> port_closed
✓ 'Serial connection lost' -> serial_connection_lost
✓ 'Bad file descriptor' -> bad_file_descriptor
✓ 'write failed: [Errno 9]' -> bad_file_descriptor
```

### **read_parameters Detection:**
```
✓ 'Serial connection lost - file descriptor is None or port is closed' -> DETECTED
✓ Will trigger enhanced recovery actions:
  - Consecutive error tracking
  - Cache clearing
  - Port reconnection
  - Temporary disabling after 10 errors
  - 1 second extra delay for rescheduling
```

## Recovery Mechanisms

### **For Your Specific Error (`port_closed`):**

1. **Immediate Actions:**
   - Clear shared instrument cache for the address
   - Clear parameter cache to force fresh lookup
   - Force port reconnection (recreate master)

2. **Consecutive Error Tracking:**
   - Track errors per address independently
   - Reset count after 30 seconds of no errors
   - Temporarily disable after 10 consecutive errors
   - Auto re-enable after 60-second recovery period

3. **Recovery Delays:**
   - **0.5 seconds** for port_closed errors (medium severity)
   - **1.0 seconds** additional delay when rescheduling after serial errors

4. **Enhanced Logging:**
   - Error type: `SERIAL_CONNECTION_LOST`
   - Error details include consecutive error count
   - Port and address context for debugging

## Expected Behavior

When the error occurs again, the system will:

1. **Detect** the error in `read_parameters` exception handler
2. **Track** consecutive errors for address 6 on `/dev/ttyUSB0`
3. **Clear** all cached instruments and parameters
4. **Reconnect** the port by recreating the master connection
5. **Log** the error with enhanced context
6. **Reschedule** polling with 1-second extra delay
7. **Reset** error count when communication is restored
8. **Temporarily disable** the address if 10 consecutive errors occur
9. **Auto re-enable** after 60-second recovery period

## Backward Compatibility

- ✅ All existing functionality preserved
- ✅ No breaking changes to APIs
- ✅ Enhanced features work transparently
- ✅ Original error handling still functional

## Files Modified

- `backend/poller.py` - Enhanced error handling and recovery
- `backend/manager.py` - Address validation (previously)
- `test_serial_connection_lost.py` - Verification tests
- `USB_ERROR_HANDLING.md` - Documentation

The system should now handle the "Serial connection lost - file descriptor is None or port is closed" error much more robustly with comprehensive recovery mechanisms.