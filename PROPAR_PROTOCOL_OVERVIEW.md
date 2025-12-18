# PROPAR Communication Protocol Overview

## Summary

**PROPAR** is a binary communication protocol used by Bronkhorst instruments (like the EL-FLOW mass flow controllers) for parameter read/write operations over serial connections.

## Physical Layer

- **Connection**: Serial RS232 / USB-to-Serial adapter
- **Baudrate**: 38,400 bps (configurable)
- **Timeout**: 2000 ms for response (increased from 500 ms for reliability with slow instruments)
- **Port Examples**: `COM1` (Windows), `/dev/ttyUSB0` (Linux)

## Protocol Mode

- **Binary Mode** (PP_MODE_BINARY = 0): Default mode used in FlowControl
- **ASCII Mode** (PP_MODE_ASCII = 1): Alternative mode (not used)

## Frame Structure

### Binary Frame Format

```
┌─────────────┬──────────────┬─────────────┬──────────────┬─────────────┐
│  DLE + STX  │  Message Data │  DLE + ETX  │              │             │
│  (Start)    │   (Body)      │   (End)     │              │             │
└─────────────┴──────────────┴─────────────┴──────────────┴─────────────┘
   0x10 0x02     [Variable]      0x10 0x03

BYTE_DLE = 0x10  (Data Link Escape - frame delimiter)
BYTE_STX = 0x02  (Start of Text)
BYTE_ETX = 0x03  (End of Text)
```

### Message Data Structure

Within the frame payload, the message contains:

```
Byte 0:     Sequence Number (SEQ)     - 0x00-0xFF, increments with each request
Byte 1:     Node Address (NODE)        - 0x01-0x7F (instrument address), 0x80 (local host)
Byte 2:     Data Length (LEN)          - 0x00-0xFF (length of command data)
Byte 3..n:  Command Data (DATA)        - Variable length command payload
```

**Message Format in Memory:**
```
[SEQ] [NODE] [LEN] [DATA...]
```

### Data Payload Encoding

The message data contains a command byte followed by parameters:

```
[COMMAND] [PROC_INDEX] [PARM_INDEX | TYPE] [PARM_DATA...]
```

#### Commands (1 byte)

| Value | Name | Description |
|-------|------|-------------|
| 0x00  | PP_COMMAND_STATUS | Status message (response) |
| 0x01  | PP_COMMAND_SEND_PARM_WITH_ACK | Send parameter with acknowledgement |
| 0x02  | PP_COMMAND_SEND_PARM | Send parameter without acknowledgement |
| 0x03  | PP_COMMAND_SEND_PARM_BROADCAST | Broadcast parameter to all nodes |
| 0x04  | PP_COMMAND_REQUEST_PARM | Request parameter from instrument |

#### Process/Parameter Indices

- **PROC_INDEX** (1 byte): Process number (0-127)
  - Bit 7 set (0x80) if chaining to next process
- **PARM_INDEX | TYPE** (1 byte): Parameter number + data type
  - Bits 0-4: Parameter number (0-31)
  - Bits 5-7: Data type (packed in upper 5 bits)
  - Bit 7 of value set (0x80) if chaining to next parameter

#### Parameter Data Types

| Code | Name | Size | Description |
|------|------|------|-------------|
| 0x00 | PP_TYPE_INT8 | 1 byte | 8-bit integer |
| 0x20 | PP_TYPE_INT16 | 2 bytes | 16-bit integer (unsigned) |
| 0x21 | PP_TYPE_SINT16 | 2 bytes | 16-bit signed integer |
| 0x22 | PP_TYPE_BSINT16 | 2 bytes | Bronkhorst signed 16-bit |
| 0x40 | PP_TYPE_INT32 | 4 bytes | 32-bit integer |
| 0x41 | PP_TYPE_FLOAT | 4 bytes | 32-bit IEEE float |
| 0x60 | PP_TYPE_STRING | Variable | Null-terminated string (max 61 bytes) |

#### Data Encoding

- **INT8**: Single byte value
- **INT16/SINT16/BSINT16**: Two bytes, big-endian (MSB first)
- **INT32**: Four bytes, big-endian
- **FLOAT**: IEEE 754 single-precision, big-endian format
- **STRING**: ASCII characters, null-terminated

## Message Types

### 1. Request Parameter (READ)

Master → Instrument: Request to read parameter value

```
Command:     0x04 (REQUEST_PARM)
Structure:   [SEQ] [NODE] [LEN] [0x04] [PROC_IDX] [PARM_IDX|TYPE]...

Example (Read parameter 205 = fMeasure as FLOAT):
SEQ=1, NODE=3, LEN=3
[0x01] [0x03] [0x03] [0x04] [0x00] [0xCD|0x41]
                      ^     ^      ^
                    CMD   PROC   PARM(205) | TYPE_FLOAT(0x41)
```

### 2. Send Parameter (WRITE)

Master → Instrument: Write parameter value to instrument

```
Command:     0x01 (SEND_PARM_WITH_ACK) or 0x02 (SEND_PARM)
Structure:   [SEQ] [NODE] [LEN] [CMD] [PROC_IDX] [PARM_IDX|TYPE] [DATA...]

Example (Write setpoint 50% to parameter 9 as INT16):
SEQ=2, NODE=3, LEN=7
[0x02] [0x03] [0x07] [0x01] [0x00] [0x09|0x20] [0x7D] [0x00]
                      ^     ^      ^           ^    ^
                    WITH_ACK PROC  PARM(9)|INT16  DATA(32000)
```

### 3. Status Response (WRITE ACK)

Instrument → Master: Acknowledgement of write operation

```
Command:     0x00 (STATUS)
Structure:   [SEQ] [NODE] [LEN] [0x00] [STATUS] [POSITION]

Status Codes (selected):
0x00 = PP_STATUS_OK (success)
0x19 = PP_STATUS_TIMEOUT_ANSWER (25 - timeout waiting for response)
0x04 = PP_STATUS_PARM_NUMBER (unknown parameter number)
0x06 = PP_STATUS_PARM_VALUE (invalid parameter value)

Example (ACK for write):
[0x02] [0x03] [0x03] [0x00] [0x00] [0x00]
       ^              ^      ^
      NODE          CMD    STATUS_OK
```

### 4. Send Parameter Response (READ RESPONSE)

Instrument → Master: Parameter data in response to request

```
Command:     0x02 (SEND_PARM)
Structure:   [SEQ] [NODE] [LEN] [0x02] [PROC_IDX] [PARM_IDX|TYPE] [DATA...]

Example (Response with fMeasure value = 45.67 as FLOAT):
[0x01] [0x03] [0x07] [0x02] [0x00] [0xCD|0x41] [0x42] [0x36] [0x76] [0x66]
                              ^      ^          ^            ^
                              PROC  PARM|TYPE  fMeasure(45.67 in IEEE 754)
```

## Parameter Organization

### Process/Parameter Structure

Instruments organize parameters hierarchically:

- **Process (proc_nr)**: 0-127, represents a subsystem (e.g., measurement, setpoint control)
- **Parameter (parm_nr)**: 0-31 per process, specific parameter within that process
- **DDE Number**: High-level abstraction combining process and parameter

### Common DDE Parameters (from poller.py)

| DDE | Process | Parameter | Type | Description |
|-----|---------|-----------|------|-------------|
| 8 | 1 | 0 | INT16 | Measure (0-32000 = 0-100%) |
| 9 | 1 | 1 | INT16 | Setpoint (0-32000 = 0-100%) |
| 21 | 1 | 5 | FLOAT | Capacity |
| 24 | 1 | 8 | INT8 | Fluid index |
| 25 | 1 | 9 | STRING | Fluid name |
| 90 | 113 | 1 | STRING | Device type |
| 92 | ? | ? | ? | Device ID |
| 115 | ? | ? | STRING | User tag |
| 175 | ? | ? | INT8 | Identification number (device type code) |
| 205 | ? | ? | FLOAT | fMeasure (flow in engineering units) |
| 206 | ? | ? | FLOAT | fSetpoint (setpoint in engineering units) |

## Data Escaping (Byte Stuffing)

Since 0x10 (DLE) is used as a frame delimiter, any occurrence of 0x10 in the message data must be escaped:

```
Message Data Contains:     Transmitted As:
    0x10                   0x10 0x10 (DLE escaped)
    
Frame Structure with Escaping:
DLE STX [DATA with 0x10→0x10 0x10] DLE ETX
0x10 0x02 [message bytes, double any 0x10] 0x10 0x03
```

### Example with Escaping

If message data is: `[0x01] [0x03] [0x10] [0x02]`

Transmitted frame becomes:
```
0x10 0x02 0x01 0x03 0x10 0x10 0x02 0x10 0x03
└─ Frame Start ─┘     └─ Escaped 0x10 ─┘  └─ Frame End ─┘
```

## State Machine: Binary Frame Reception

The receiver uses a state machine to parse frames:

```
START_1: Wait for DLE (0x10)
    ├─ Receive DLE → go to START_2
    └─ Other byte → signal as non-propar data

START_2: Wait for STX (0x02) after DLE
    ├─ Receive STX → go to MESSAGE_DATA
    └─ Other byte → ERROR state

MESSAGE_DATA: Receive message payload bytes
    ├─ Receive DLE → go to MESSAGE_DATA_OR_END
    └─ Other byte → add to buffer, stay in MESSAGE_DATA

MESSAGE_DATA_OR_END: After receiving DLE, check next byte
    ├─ Receive DLE → add one DLE to buffer (unescape), go to MESSAGE_DATA
    ├─ Receive ETX (0x03) → message complete, go to START_1
    └─ Other byte → ERROR state

ERROR: Frame error detected
    → go back to START_1, wait for next frame
```

## Parameter Chaining

Multiple parameters can be sent in a single message by "chaining":

- **Process Chaining**: Multiple parameters from different processes
  - Set bit 7 of PROC_INDEX (0x80) to indicate next parameter in different process
- **Parameter Chaining**: Multiple parameters within same process
  - Set bit 7 of PARM_INDEX (0x80) to indicate next parameter

Example:

```
Send two parameters: [proc=0, parm=1, data=10] and [proc=0, parm=2, data=20]

[COMMAND] [PROC|0x80] [PARM1|TYPE|0x80] [DATA1] [PARM2|TYPE] [DATA2]
                ^                           ^      No proc byte needed
            Chain indicator              Chain indicator (last)
```

## Status Codes

| Code | Name | Description |
|------|------|-------------|
| 0 | PP_STATUS_OK | Operation successful |
| 1 | PP_STATUS_PROCESS_CLAIMED | Process already in use |
| 2 | PP_STATUS_COMMAND | Unknown command |
| 3 | PP_STATUS_PROC_NUMBER | Unknown process number |
| 4 | PP_STATUS_PARM_NUMBER | Unknown parameter number |
| 5 | PP_STATUS_PARM_TYPE | Invalid parameter type |
| 6 | PP_STATUS_PARM_VALUE | Invalid parameter value |
| 7 | PP_STATUS_NETWORK_NOT_ACTIVE | Network not active |
| 8 | PP_STATUS_TIMEOUT_START_CHAR | Timeout waiting for start character |
| 9 | PP_STATUS_TIMEOUT_SERIAL_LINE | Timeout on serial line |
| ... | ... | ... |
| 25 | PP_STATUS_TIMEOUT_ANSWER | **Timeout waiting for response** (most common error) |
| ... | ... | ... |

## Request/Response Sequence

### Typical Read Flow

```
Master                                  Instrument
  │                                         │
  │  [REQUEST_PARM] SEQ=1, NODE=3         │
  ├──────────────────────────────────────→ │
  │                                         │ (process request)
  │        [SEND_PARM] SEQ=1, NODE=3       │
  │ ←──────────────────────────────────────┤
  │                                         │
```

### Typical Write with ACK Flow

```
Master                                  Instrument
  │                                         │
  │  [SEND_PARM_WITH_ACK] SEQ=2, NODE=3   │
  ├──────────────────────────────────────→ │
  │                                         │ (store value)
  │        [STATUS] SEQ=2, STATUS=OK        │
  │ ←──────────────────────────────────────┤
  │                                         │
```

## Timeout Behavior

- **Response Timeout**: 2000 ms (increased from 500 ms)
  - If no response received within timeout, instrument is assumed unresponsive
  - Status code: PP_STATUS_TIMEOUT_ANSWER (0x19)
  - Retry with progressive delays: 0.02s, 0.04s, 0.06s, 0.08s, 0.1s

- **Serial Communication Timeout**: 10 ms per byte
  - Part of serial port configuration

## Implementation Details in FlowControl

### Message Builder (`_propar_builder`)

Handles:
- Parameter chaining logic
- Data type encoding (INT, FLOAT, STRING)
- Message framing and validation
- Parameter size calculation

### Serial Provider (`_propar_provider`)

Handles:
- Serial port I/O in separate thread
- Frame reception with byte stuffing
- Binary protocol state machine
- Queue management for messages

### Master Class

Handles:
- Sequence number management (auto-increment)
- Request/response matching
- Timeout and retry logic
- Callback handling for async operations

### Instrument Class

High-level wrapper that:
- Maps DDE numbers to process/parameter numbers
- Converts between engineering units and raw values
- Provides convenient read/write methods
- Manages multi-instrument communication on single port

## Optimization Features Used

1. **Thread-Safe Wrapper** (`ThreadSafeProparInstrument`)
   - Single-threaded access per port (prevents "Bad file descriptor" errors)
   - Progressive retry delays

2. **Reliable Polling** (200 ms intervals)
   - Not too fast (avoids overwhelming slow instruments)
   - Not too slow (maintains responsiveness)

3. **Extended Timeouts** (2000 ms)
   - 4x longer than original (500 ms)
   - Accommodates slow USB converters and instruments

4. **Reply-Based Sequencing**
   - Wait for actual response rather than fixed delays
   - Better performance when instruments respond quickly

## References

- **Protocol**: Bronkhorst PROPAR Binary Protocol
- **Instruments**: EL-FLOW mass flow controllers
- **Interface**: Serial RS232 / USB-to-Serial
- **Implementation**: `propar_new/__init__.py` (1856 lines)
