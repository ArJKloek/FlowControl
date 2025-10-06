# Capacity Validation Implementation Summary

## Overview
Added capacity validation to the FlowControl poller system to prevent unrealistic flow measurements from reaching the UI and telemetry systems.

## Changes Made

### 1. Parameter 175 (IDENT_NR_DDE) Integration
- **Added**: `IDENT_NR_DDE = 175` constant for device identification
- **Purpose**: Distinguish between device types (DMFC, DMFM, etc.)
- **Usage**: Reads identification number to categorize instruments

### 2. Device Type Detection
Added automatic detection of instrument types based on parameter 175:
- **7**: DMFC (Digital Mass Flow Controller)
- **8**: DMFM (Digital Mass Flow Meter) 
- **9**: DEPC (Digital Electronic Pressure Controller)
- **10**: DEPM (Digital Electronic Pressure Meter)
- **12**: DLFC (Digital Liquid Flow Controller)
- **13**: DLFM (Digital Liquid Flow Meter)

### 3. Capacity Validation Logic (DMFC Only)
- **Rule**: Skip measurements where `FMEASURE > (CAPACITY × 1.5)` **ONLY for DMFC instruments**
- **Device Filter**: Only applies to instruments with `IDENT_NR = 7` (DMFC)
- **Threshold**: 150% of instrument capacity
- **Bypass**: All other device types (DMFM, DLFC, DLFM, DEPC, DEPM) bypass validation
- **Safety**: Handles None/invalid values gracefully
- **Logging**: Warning messages specifically mention "DMFC validation"

### 4. Enhanced Telemetry
When measurements are skipped, the system emits telemetry with:
- Timestamp and instrument details
- Validation skip reason
- Actual vs. threshold values
- Error categorization

## Code Locations

### Constants (lines 6-16)
```python
FSETPOINT_DDE = 206     # fSetpoint
FMEASURE_DDE = 205      # fMeasure
FIDX_DDE = 24           # fluid index
FNAME_DDE = 25          # fluid name
SETPOINT_DDE = 9        # setpoint (int, 32000 100%)
MEASURE_DDE = 8         # measure (int, 32000 100%)
USERTAG_DDE = 115       # usertag
CAPACITY_DDE = 21       # capacity (float)
TYPE_DDE = 90           # type (string)
IDENT_NR_DDE = 175      # identification number (device type code)
```

### Parameter Reading (line ~334)
```python
PARAMS = [FMEASURE_DDE, FNAME_DDE, MEASURE_DDE, SETPOINT_DDE, 
          FSETPOINT_DDE, CAPACITY_DDE, TYPE_DDE, IDENT_NR_DDE]
```

### Validation Logic (lines ~342-365)
```python
# Validate FMEASURE against CAPACITY (skip if > 150% of capacity)
# Only apply validation to DMFC instruments (ident_nr == 7)
skip_measurement = False
if (ident_nr == 7 and  # Only for DMFC instruments
    capacity_value is not None and fmeasure_value is not None):
    try:
        capacity_150_percent = float(capacity_value) * 1.5
        if float(fmeasure_value) > capacity_150_percent:
            skip_measurement = True
            print(f"⚠️  {self.port}/{address}: DMFC validation - Skipping measurement...")
    except (ValueError, TypeError):
        pass
```

## Benefits

### Data Quality
- **Prevents** unrealistic spikes from reaching UI
- **Maintains** consistent measurement ranges
- **Filters** sensor errors and communication glitches

### System Reliability  
- **Protects** downstream systems from bad data
- **Preserves** telemetry integrity
- **Enables** better trend analysis

### Debugging Support
- **Clear warnings** when measurements are skipped
- **Detailed telemetry** for troubleshooting
- **Device identification** for targeted maintenance

## Testing

### Test Scripts Created
1. `test_device_type_detection.py` - Verifies parameter 175 mapping
2. `test_capacity_validation.py` - Tests validation threshold logic  
3. `test_complete_validation.py` - End-to-end simulation

### Test Scenarios Covered
- Normal measurements within capacity
- Edge cases at exactly 150% threshold
- Measurements exceeding 150% (should skip)
- Missing data handling (None values)
- Different device types (DMFC, DMFM, etc.)

## Usage Example

When the poller detects a DMFC measurement exceeding 150% of capacity:

```
⚠️  COM3/5: DMFC validation - Skipping measurement - FMEASURE (30.100) exceeds 150% of capacity (30.000)
```

The telemetry system receives:
```python
{
    "ts": 1696550400.123,
    "port": "COM3", 
    "address": 5,
    "kind": "validation_skip",
    "name": "dmfc_capacity_exceeded",
    "value": 30.1,
    "capacity": 20.0,
    "threshold": 30.0,
    "device_type": "DMFC",
    "reason": "DMFC validation: FMEASURE (30.100) > 150% capacity (30.000)"
}
```

**Note**: DMFM, DLFC, DLFM and other devices bypass this validation entirely.

## Configuration

No configuration required - validation is automatic based on:
- **Device type**: Only DMFC instruments (IDENT_NR = 7)
- Instrument capacity (parameter 21)
- Current flow measurement (parameter 205)
- Fixed 150% threshold

**Key Point**: DMFM (meters) and other device types are not subject to this validation.

## Impact on Existing Code

### Minimal Changes
- Existing measurement flow unchanged for valid data
- New validation happens before emission
- UI receives same data structure with additional fields

### Backward Compatibility
- All existing parameters still available
- New fields (`device_category`, `ident_nr`) added
- Legacy systems ignore new fields automatically

## Future Enhancements

### Configurable Thresholds
- Could make 150% threshold user-configurable
- Different thresholds per device type
- Dynamic adjustment based on operating conditions

### Advanced Validation
- Rate-of-change limits
- Multiple-sample validation
- Statistical outlier detection

### Integration Options
- Error logging to database
- Email alerts for persistent issues
- Automatic recalibration triggers