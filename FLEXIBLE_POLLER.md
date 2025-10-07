# Flexible PortPoller Implementation

This document describes the enhanced PortPoller implementation that supports both single-instrument and multi-instrument polling scenarios.

## Overview

The flexible PortPoller enhances the original polling architecture to support:

1. **Single-address mode**: One instrument per USB adapter (backward compatible)
2. **Multi-address mode**: Multiple instruments on a single RS232 bus via one USB adapter
3. **Auto-configuration**: Automatic detection and optimal poller setup

## Architecture

### PortPoller Class Enhancements

The `PortPoller` class now accepts an optional `addresses` parameter:

```python
def __init__(self, manager, port, addresses=None, default_period=0.5):
    """
    Args:
        addresses (int|list|None): 
            - None: Dynamic discovery (backward compatible)
            - int: Single address mode
            - list: Multi-address mode
    """
```

### Address Handling

- **Dynamic**: `addresses=None` - Instruments added via `add_node()`
- **Single**: `addresses=1` - One instrument at address 1
- **Multi**: `addresses=[1,2,3]` - Three instruments on same bus

## Usage Examples

### 1. Backward Compatible (Original Behavior)

```python
# Original usage - still works exactly the same
poller = PortPoller(manager, "COM3")
poller.add_node(1)  # Add instrument at address 1
```

### 2. Single-Address Mode

```python
# Explicitly configure for one instrument
poller = PortPoller(manager, "COM3", addresses=1)
# Address 1 is automatically added to polling queue
```

### 3. Multi-Address Mode

```python
# Multiple instruments on RS232 bus
poller = PortPoller(manager, "COM3", addresses=[1, 2, 3])
# All three addresses automatically added to polling queue
```

### 4. Manager Auto-Configuration

```python
# Let Manager decide based on discovered instruments
manager.scan()  # Discover instruments
manager.auto_configure_pollers()  # Create optimal pollers
```

## ProPar Protocol Support

The ProPar protocol already supports multi-address communication:

- **Shared masters**: `_PROPAR_MASTERS` dictionary prevents port conflicts
- **Address parameter**: Each instrument call includes `node=address`
- **Sequential access**: Thread-safe access to shared serial ports

## Polling Coordination

### Fair Scheduling

For multi-address pollers:
- Round-robin address selection
- Fairness tracking per address
- Small delays between operations

### USB Device Sharing

- Shared instrument cache per port
- Coordinated access via Manager
- Minimal delays to reduce USB contention

## Manager Methods

### Auto-Configuration

```python
def auto_configure_pollers(self, default_period=0.5) -> Dict[str, List[int]]:
    """Automatically configure pollers based on discovered nodes."""
```

### Explicit Configuration

```python
def create_single_address_poller(self, port: str, address: int) -> PortPoller:
    """Create poller for single instrument."""

def create_multi_address_poller(self, port: str, addresses: List[int]) -> PortPoller:
    """Create poller for multiple instruments on RS232 bus."""
```

## Configuration Scenarios

### Scenario 1: Individual USB Adapters

```
USB-1 (COM3) -> Instrument A (address 1)
USB-2 (COM4) -> Instrument B (address 1)
USB-3 (COM5) -> Instrument C (address 1)
```

**Configuration:**
```python
manager.create_single_address_poller("COM3", 1)
manager.create_single_address_poller("COM4", 1)
manager.create_single_address_poller("COM5", 1)
```

### Scenario 2: RS232 Bus

```
USB-1 (COM3) -> RS232 Bus -> Instrument A (address 1)
                          -> Instrument B (address 2)
                          -> Instrument C (address 3)
```

**Configuration:**
```python
manager.create_multi_address_poller("COM3", [1, 2, 3])
```

### Scenario 3: Mixed Setup

```
USB-1 (COM3) -> Instrument A (address 1)
USB-2 (COM4) -> RS232 Bus -> Instrument B (address 1)
                          -> Instrument C (address 2)
```

**Configuration:**
```python
manager.create_single_address_poller("COM3", 1)
manager.create_multi_address_poller("COM4", [1, 2])
```

## Backward Compatibility

The implementation maintains 100% backward compatibility:

1. **Existing code**: Works without changes
2. **add_node()**: Still works for dynamic discovery
3. **Manager.ensure_poller()**: Unchanged behavior when no addresses specified

## Error Handling

- **Port conflicts**: Prevents multiple pollers on same port
- **Address validation**: Ensures valid ProPar addresses (1-247)
- **USB contention**: Coordinated access reduces conflicts

## Testing

Use `test_flexible_poller.py` to verify functionality:

1. **Scan**: Discover available instruments
2. **Auto-config**: Let system choose optimal configuration
3. **Manual**: Test specific single/multi-address scenarios
4. **Monitoring**: Watch polling performance and fairness

## Performance Considerations

### Single-Address Mode
- Identical to original implementation
- No overhead from multi-address logic

### Multi-Address Mode
- Round-robin scheduling ensures fairness
- Small delays prevent USB bus saturation
- Shared caching reduces redundant operations

## Implementation Files

- `backend/poller.py`: Enhanced PortPoller class
- `backend/manager.py`: Auto-configuration methods
- `test_flexible_poller.py`: Test application
- `FLEXIBLE_POLLER.md`: This documentation