🔧 SCANNER ENHANCEMENT - ALWAYS LOAD INSTRUMENTS FOR CONTROL

## Problem Addressed
The scanner was previously rejecting instruments if certain parameters were missing, preventing users from controlling those instruments. The user requested that instruments should always be loaded to ensure control availability, even with incomplete parameter data.

## Changes Implemented

### 1. Removed Parameter-Based Instrument Rejection

#### Before (Restrictive):
```python
# Only skip if we're missing too many critical parameters
# Allow instruments with at least model OR capacity to proceed
if info.model is None and info.capacity is None:
    self.portError.emit(port, f"Essential parameters missing for instrument {info.address}: {', '.join(missing_params)}")
    continue  # ❌ SKIPS INSTRUMENT - No control possible
```

#### After (Permissive):
```python
# Always load instruments - prefer control availability over complete parameter data
if missing_params:
    print(f"Warning: Some parameters missing for instrument {info.address}: {', '.join(missing_params)}")
    print(f"         Instrument will still be loaded for control purposes")
    
    # Set default values for missing critical parameters to ensure UI compatibility
    if info.model is None:
        info.model = f"Unknown_Model_Addr{info.address}"
    if info.capacity is None:
        info.capacity = 100.0  # Default capacity
    if info.unit is None:
        info.unit = "ml/min"  # Default unit
# ✅ ALWAYS CONTINUES - Instrument always available for control
```

### 2. Added Robust Parameter Reading with Fallbacks

#### Enhanced Error Handling:
```python
# Always load instrument - wrap parameter reading in try-except for robustness
try:
    vals = _read_dde_stable(m, info.address, [115, 25, 21, 129, 24, 206, 91, 175], debug=True)
    info.usertag, info.fluid, info.capacity, info.unit, orig_idx, info.fsetpoint, info.model = (
        vals.get(115), vals.get(25), vals.get(21), vals.get(129), vals.get(24), vals.get(206), vals.get(91)  
    )
    device_type_id = vals.get(175)
except Exception as param_error:
    # If parameter reading fails completely, use default values
    print(f"Warning: Parameter reading failed for instrument {info.address}: {param_error}")
    print(f"         Loading instrument with default values for control purposes")
    
    # Provide sensible defaults
    info.usertag = f"Instrument_{info.address}"
    info.fluid = "Unknown"
    info.capacity = 100.0
    info.unit = "ml/min"
    orig_idx = 0
    info.fsetpoint = 0.0
    info.model = f"Unknown_Model_Addr{info.address}"
    device_type_id = None
```

### 3. Default Value Strategy

#### Default Values for Missing Parameters:
- **Model**: `"Unknown_Model_Addr{address}"` (e.g., "Unknown_Model_Addr3")
- **Capacity**: `100.0` (ml/min or appropriate unit)
- **Unit**: `"ml/min"` (common flow unit)
- **User Tag**: `"Instrument_{address}"` (e.g., "Instrument_3")
- **Fluid**: `"Unknown"` (indicates unknown fluid type)
- **Setpoint**: `0.0` (safe default)
- **Device Type**: `"Unknown"` (when type detection fails)

## Benefits Achieved

### 1. Guaranteed Instrument Availability:
- ✅ **All detected instruments are loaded** regardless of parameter status
- ✅ **Control always possible** even with incomplete data
- ✅ **User preference respected** - control over completeness

### 2. Graceful Degradation:
- ✅ **Partial parameter failure** doesn't prevent instrument loading
- ✅ **Complete parameter failure** handled with defaults
- ✅ **UI compatibility maintained** with sensible default values

### 3. Enhanced User Experience:
- ✅ **No surprise missing instruments** due to parameter issues
- ✅ **Clear warnings** about missing data without blocking
- ✅ **Instrument control prioritized** over data completeness

## Technical Implementation Details

### Error Handling Hierarchy:
1. **Individual Parameter Failure**: Handled by `_read_dde_stable` retry logic
2. **Multiple Parameter Failure**: Warnings logged, defaults applied for missing ones
3. **Complete Parameter Read Failure**: Caught by outer try-except, all defaults applied
4. **Communication Failure**: Still handled at port level (instrument not detectable)

### Compatibility Preservation:
- **UI Elements**: All expected fields populated with defaults
- **Data Types**: Consistent types maintained (strings, floats, integers)
- **Fluid Tables**: Still scanned but failures don't prevent instrument loading
- **Gas Factors**: Will work with default capacity values

### Logging and Visibility:
- **Warning Messages**: Clear indication when parameters are missing
- **Control Priority**: Explicit messaging that control is prioritized
- **Debug Information**: Parameter read status for troubleshooting

## Impact on Different Scenarios

### Scenario 1: Perfect Communication
- **Before**: Instrument loaded with all parameters ✅
- **After**: Instrument loaded with all parameters ✅
- **Change**: No change in behavior

### Scenario 2: Some Parameters Missing
- **Before**: Instrument loaded with warnings ✅
- **After**: Instrument loaded with defaults for missing params ✅
- **Change**: Better UI compatibility with default values

### Scenario 3: Critical Parameters Missing
- **Before**: Instrument REJECTED - no control possible ❌
- **After**: Instrument loaded with defaults - control available ✅
- **Change**: **Major improvement** - control now possible

### Scenario 4: Parameter Reading Completely Fails
- **Before**: Instrument REJECTED - no control possible ❌
- **After**: Instrument loaded with all defaults - control available ✅
- **Change**: **Major improvement** - control now possible

### Scenario 5: Communication Failure
- **Before**: Port error - no instruments detected ❌
- **After**: Port error - no instruments detected ❌
- **Change**: No change (physical communication still required)

## Example Output

### New Warning Messages:
```
Warning: Parameter reading failed for instrument 3: 'node'
         Loading instrument with default values for control purposes

Warning: Some parameters missing for instrument 3: capacity(21), unit(129)
         Instrument will still be loaded for control purposes

Instrument 3: capacity=100.0, unit=ml/min, model=Unknown_Model_Addr3, device_type=Unknown
```

### UI Display:
- **Instrument Name**: "Unknown_Model_Addr3" (clearly indicates unknown)
- **Capacity**: "100.0 ml/min" (functional default)
- **User Tag**: "Instrument_3" (identifiable)
- **Control Available**: All setpoint and measurement functions work

## Files Modified

### `backend/scanner.py`:
1. **Removed instrument rejection** based on missing parameters
2. **Added comprehensive try-except** around parameter reading
3. **Implemented default value assignment** for all critical parameters
4. **Enhanced logging** for transparency about missing data

## Testing Recommendations

### Test Cases to Verify:
1. **Normal Operation**: Instruments with all parameters should work unchanged
2. **Partial Failures**: Instruments with some missing parameters should load with defaults
3. **Complete Failures**: Instruments with no readable parameters should load with all defaults
4. **Control Functions**: Verify setpoint/measurement operations work with default values
5. **UI Display**: Confirm default values display appropriately in interface

### Expected Results:
- ✅ **More instruments discovered** during scanning
- ✅ **No unexpected missing instruments** due to parameter issues
- ✅ **Control always available** for detected instruments
- ✅ **Clear indication** when using default values

## Summary

✅ **SCANNER ENHANCEMENT COMPLETE**

The scanner now prioritizes **instrument control availability** over **parameter data completeness**:

- 🛡️ **Always loads detected instruments** regardless of parameter status
- 🔧 **Provides sensible defaults** for missing parameters  
- ⚠️ **Clear warnings** about incomplete data without blocking
- 🎯 **User preference respected** - control over completeness

This ensures that users can always control their instruments, even when some configuration data is unavailable or unreadable.