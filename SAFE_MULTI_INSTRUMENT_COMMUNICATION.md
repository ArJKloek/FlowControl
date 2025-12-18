# Safe Multi-Instrument Communication over Shared Serial

## Overview

When multiple instruments (addresses 3, 5, 6) are connected to the same serial port (`/dev/ttyUSB0`), they share a single USB-to-Serial adapter. This creates potential for **communication conflicts** if multiple threads try to access the port simultaneously. Your FlowControl system implements **multiple layers of safety mechanisms** to handle this.

---

## Layer 1: Port-Level Locking (SerialPortManager)

### Problem
Without synchronization, concurrent serial writes/reads cause:
- **"Bad file descriptor"** errors
- USB adapter crashes
- Corrupted data frames
- Sequence number mismatches

### Solution: RLock per Port

```python
class SerialPortManager:
    def __init__(self):
        self._port_locks: Dict[str, threading.RLock] = {}  # One lock per port
        
    def get_port_lock(self, port: str) -> threading.RLock:
        """Get or create a lock for the port"""
        if port not in self._port_locks:
            self._port_locks[port] = threading.RLock()
        return self._port_locks[port]
    
    @contextmanager
    def acquire_port(self, port: str):
        """Context manager for exclusive port access"""
        port_lock = self.get_port_lock(port)
        
        # Only ONE thread can hold this lock at a time
        if not port_lock.acquire(blocking=False):
            logger.debug(f"Port {port} busy, waiting...")
            port_lock.acquire()  # Block until available
        
        try:
            yield  # Critical section - exclusive port access
        finally:
            port_lock.release()
```

**Key Features:**
- **RLock** (recursive lock): Same thread can acquire multiple times
- **Per-port isolation**: Different ports can be accessed in parallel
- **Mutual exclusion**: Only ONE operation per port at any time
- **Blocking queue**: Threads wait for access to become available

### Example: Two Threads, One Port

```
Thread A                          Thread B                      Serial Port
│                                │                            │
├─ acquire_port(/dev/ttyUSB0) ──→│                        ─→ LOCKED
│                                ├─ try_acquire (BLOCKED)  
│  [execute read]                │                           
│  [wait for response]            │                           
│                                │                           
├─ release_port ────────────────→│                        ─→ UNLOCKED
│                                ├─ acquire_port (SUCCESS)
│                                │  [execute write]
│                                │  [wait for response]
│                                │
│                                ├─ release_port          ─→ UNLOCKED
```

---

## Layer 2: Operation Retries with Progressive Delays

### Problem
USB serial communication can fail transiently:
- Slow instruments don't respond within timeout
- USB converter needs recovery time
- Propar protocol parsing errors

### Solution: Automatic Retry with Backoff

```python
def _execute_with_retry(self, operation, operation_name, max_retries=3):
    """Execute operation with retry logic"""
    for attempt in range(max_retries + 1):
        try:
            # Acquire EXCLUSIVE port access
            with _serial_port_manager.acquire_port(self.comport):
                result = operation()
                return result
                
        except Exception as e:
            if is_recoverable_error(e):
                if attempt < max_retries:
                    # Progressive delay: 0.1s, 0.2s, 0.3s, ...
                    delay = 0.1 * (attempt + 1)
                    logger.info(f"Retry {attempt + 1}/{max_retries} after {delay}s")
                    time.sleep(delay)
                    continue
            else:
                break  # Non-recoverable, don't retry
    
    raise last_exception
```

**Retry Strategy:**
- **Attempt 1**: Immediate (try immediately)
- **Attempt 2**: Wait 0.1s (give instrument time to recover)
- **Attempt 3**: Wait 0.2s (longer delay)
- **Attempt 4**: Wait 0.3s (final attempt)

**Recoverable Errors:**
- "Bad file descriptor" (USB connection issue)
- "Device not configured" (transient state)
- "Index out of range" (Propar parsing error)
- "struct.error" (Message format issue)

---

## Layer 3: Master Instance Per Port (Shared)

### Problem
Creating multiple Master instances for the same port causes conflicts.

### Solution: Master Caching

```python
class ProparManager:
    def __init__(self):
        self._masters: Dict[str, ProparMaster] = {}  # Cache per port
        self._shared_inst_cache: Dict[str, Dict[int, ProparInstrument]] = {}
    
    def get_shared_instrument(self, port: str, address: int):
        """Get or create shared instrument for port/address"""
        if port not in self._shared_inst_cache:
            self._shared_inst_cache[port] = {}
        
        cache = self._shared_inst_cache[port]
        if address not in cache:
            # Create once, reuse forever
            cache[address] = ThreadSafeProparInstrument(port, address=address)
        
        return cache[address]
```

**Benefits:**
- **Single master per port**: All instruments on a port share one Master instance
- **Single read thread**: One background thread processes all responses for the port
- **Sequence number tracking**: Proper matching of requests/responses
- **Message queue**: FIFO processing of incoming data

---

## Layer 4: Sequence Numbers (Protocol Level)

### How It Works

Each message includes a **sequence number** (0-255):

```
Message Structure:
┌──────────┬──────────┬─────────┬──────────┐
│ SEQ (0-255)│ NODE    │ LEN     │ DATA     │
└──────────┴──────────┴─────────┴──────────┘
    ↑                   
    Incremented per request
```

### Request/Response Matching

When instruments respond, they echo the sequence number:

```
Master                          Instrument
  │                                │
  │  [REQUEST] SEQ=42, NODE=3    │
  ├──────────────────────────────→ │
  │                                │
  │      [RESPONSE] SEQ=42, DATA   │
  │ ←──────────────────────────────┤
  │                                │
  │  Match! SEQ matches, NODE matches
```

**Multiple Instruments on Same Port:**

```
Master                      Instrument 3      Instrument 5
  │                              │                  │
  │  REQ SEQ=1, NODE=3 ─────────→ │                 │
  │  REQ SEQ=2, NODE=5 ──────────────────────────→ │
  │                              │                  │
  │      RESP SEQ=2 ←──────────────────────────────┤
  │      RESP SEQ=1 ←──────────────┤                │
  │                                                  │
  │  Correct matching by SEQ number!
```

---

## Layer 5: Polled Reading Architecture

### Structure

```python
class PortPoller(QThread):
    """One poller per port, handles all instruments on that port"""
    
    def __init__(self, port, manager):
        self.port = port
        self.manager = manager
        self.nodes = {}  # Address → polling info
        self._async_commands = queue.Queue()  # Command queue
        self._pending_command = None  # Currently executing
        self._command_timeout = 0.4  # 400ms timeout
        self._reply_received = False
    
    def poll_cycle(self):
        """Execute one complete polling cycle"""
        for address in self.nodes:
            # Get shared instrument (all threads use same instance)
            inst = self.manager.get_shared_instrument(self.port, address)
            
            # Read measurements
            # (Each access automatically gets port lock)
            flow = inst.readParameter(FMEASURE_DDE)
            setpoint = inst.readParameter(FSETPOINT_DDE)
            
            # Emit data
            self.measurement_received.emit({
                'port': self.port,
                'address': address,
                'fmeasure': flow,
                'fsetpoint': setpoint
            })
```

**Polling Sequence (200 ms interval):**

```
Cycle 1: t=0ms
  ├─ Poll Address 3
  │  ├─ [acquire_port lock]
  │  ├─ Read fMeasure (45.67)
  │  ├─ Read fSetpoint (50.0)
  │  └─ [release_port lock]
  ├─ Poll Address 5
  │  ├─ [acquire_port lock]
  │  ├─ Read fMeasure (12.34)
  │  ├─ Read fSetpoint (15.0)
  │  └─ [release_port lock]
  └─ Poll Address 6
     ├─ [acquire_port lock]
     ├─ Read fMeasure (0.00)
     ├─ Read fSetpoint (0.00)
     └─ [release_port lock]

Cycle 2: t=200ms (same as Cycle 1)

Cycle 3: t=400ms (same as Cycle 1)
```

---

## Layer 6: Priority Command Buffers

### Async Command Queue

User commands (setpoint changes, fluid switches) don't block polling:

```python
class PortPoller:
    def __init__(self):
        self._async_commands = queue.Queue()  # User command queue
    
    def queue_async_command(self, address, command, args):
        """Queue a command (non-blocking)"""
        self._async_commands.put({
            'address': address,
            'command': command,
            'args': args,
            'timeout': 0.4
        })
```

**Execution Pattern:**

```
Main Thread (UI)        Polling Thread (/dev/ttyUSB0)        Instruments
  │                           │                              │
  │  queue_setpoint(3, 50)    │                              │
  └────────────────────────→  │                              │
  (returns immediately)        │                              │
                              ├─ [next poll cycle]           │
                              ├─ [acquire_port lock]         │
                              ├─ Send SETPOINT ────────────→ │
                              │                              │
                              │                    [execute]  │
                              │                              │
                              ├─ Receive ACK ←──────────────┤
                              ├─ [release_port lock]         │
                              │                              │
  (data updated on UI)    ← [emit data_updated signal]
```

**Benefits:**
- Non-blocking UI
- Commands don't interfere with polling
- Polling continues during command execution

---

## Safety Summary: Defense in Depth

| Layer | Mechanism | Protects Against |
|-------|-----------|------------------|
| **1** | RLock per port | Concurrent USB access |
| **2** | Retry with backoff | Transient failures |
| **3** | Master caching | Multiple instances on same port |
| **4** | Sequence numbers | Request/response mismatches |
| **5** | Poller architecture | Interleaved reads/writes |
| **6** | Priority commands | User UI blocking |

---

## Example: Safe Multi-Instrument Operation

### Setup
- **Port**: `/dev/ttyUSB0`
- **Instruments**: Address 3 (Nitrogen), 5 (Air), 6 (Helium)
- **Operations**: 
  - Polling all three every 200ms
  - User changes setpoint on address 3
  - System tries to recover from USB error

### Timeline

```
t=0ms:   Start polling cycle
         ├─ Address 3: [LOCK] read 45.67 [UNLOCK]
         ├─ Address 5: [LOCK] read 12.34 [UNLOCK]
         └─ Address 6: [LOCK] read  0.00 [UNLOCK]

t=50ms:  User changes setpoint on address 3 to 55.0
         └─ Queue command: async_fset_flow(3, 55.0)

t=200ms: Start polling cycle (again)
         ├─ Address 3: [LOCK] read 45.67 [UNLOCK]
         ├─ Address 5: [LOCK] read 12.34 [UNLOCK]
         ├─ Address 6: [LOCK] read  0.00 [UNLOCK]
         └─ Process queued command:
            [LOCK] write setpoint 55.0 to address 3 [UNLOCK]

t=210ms: USB error detected ("Bad file descriptor")
         └─ Retry logic:
            - Attempt 1: Failed
            - Wait 0.1s
            - Attempt 2: [LOCK] recreate master, try again [UNLOCK]

t=310ms: Continue polling normally

```

---

## Configuration: Timeouts & Polling Rates

### Current Settings (Optimized)

```python
# propar_new/__init__.py
response_timeout = 2.0  # 2000ms (was 500ms)

# thread_safe_propar.py
max_retries = 3
retry_delays = [0.1s, 0.2s, 0.3s]  # Progressive (was 0.02s, 0.04s, 0.06s)

# poller.py
default_period = 0.2  # 200ms polling (was 50ms)
command_timeout = 0.4  # 400ms per command
```

### Why These Values?

| Setting | Value | Reason |
|---------|-------|--------|
| `response_timeout` | 2.0s | Slow USB converters + slow instruments |
| `retry_delays` | Progressive | Give instrument time to recover |
| `polling_period` | 200ms | Not too fast (avoid USB congestion), not too slow (still responsive) |
| `command_timeout` | 400ms | Based on PROPAR protocol RTT |

---

## Best Practices

1. **Always use `get_shared_instrument()`**: Don't create new instrument instances
2. **One master per port**: Reuse the cached master
3. **Trust the locks**: Don't add manual locking on top
4. **Monitor statistics**: Check retry/block counters for port health
5. **Long timeouts**: 2000ms is now standard, not a mistake
6. **Async commands**: Queue user actions, don't execute immediately

---

## Monitoring Communication Health

```python
# Get statistics for a port
stats = manager.get_statistics('/dev/ttyUSB0')

print(f"Total operations: {stats['total_operations']}")
print(f"Successful: {stats['successful_operations']}")
print(f"Failed: {stats['failed_operations']}")
print(f"Concurrent attempts blocked: {stats['concurrent_attempts_blocked']}")
print(f"Longest operation: {stats['longest_operation_ms']:.1f}ms")
```

**Health Indicators:**
- **High concurrent_attempts_blocked**: Many threads competing for same port (normal during polling)
- **High failed_operations**: USB instability or slow instruments
- **longest_operation_ms > 2000ms**: Command timeout (check instrument responsiveness)

---

## Conclusion

Safe multi-instrument communication requires:

1. **Serialization**: One operation per port at a time (RLock)
2. **Reliability**: Retry transient failures with backoff
3. **Organization**: Single master per port, sequence-matched responses
4. **Architecture**: Polling prevents reader thread starvation
5. **Async handling**: Commands don't block polling

Your system implements all of these, making it safe for multiple instruments on a single serial port! ✅
