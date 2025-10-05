#!/usr/bin/env python3
"""
How to test extreme value capping in FlowControl application:

1. SETUP:
   - Run the main FlowControl application with dummy instruments enabled
   - Open a meter dialog or control dialog for a dummy instrument

2. ENABLE EXTREME TESTING:
   From Python console or script, access the dialog and enable testing:
   
   # For meter dialog:
   meter_dialog._enable_extreme_testing(True, 5)  # Every 5 measurements
   
   # Or directly access the instrument:
   instrument = manager.instrument("dummy_CO2", 1)  # or dummy_H2
   instrument.enable_extreme_test(True, 10)  # Every 10 measurements

3. OBSERVE:
   - Watch the flow measurements in the dialog
   - Extreme values (1.0e+07) will be generated periodically
   - Status should show: "Flow capped: 1.0e+07 → 200.0 (>200% capacity)"
   - Display value should be capped at 200.0 (for 100 ln/min capacity)

4. DISABLE TESTING:
   meter_dialog._enable_extreme_testing(False)
   # or
   instrument.enable_extreme_test(False)

5. VERIFICATION:
   - Extreme values are generated every N measurements
   - Values above 200% of capacity (200.0 for 100 ln/min) are capped
   - Warning message appears in status display
   - Capped values are used for display and logging instead of extreme values

EXPECTED BEHAVIOR:
- Capacity: 100.0 ln/min
- Maximum allowed: 200.0 ln/min (200% of capacity)
- Extreme test value: 1.0e+07 ln/min
- Capped display value: 200.0 ln/min
- Status warning: Shows original and capped values

This validates that the flow capping protection works correctly for instrument errors.
"""

if __name__ == "__main__":
    print(__doc__)