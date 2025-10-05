#!/usr/bin/env python3
"""
Simple test script to verify extreme value generation in dummy instrument
and test the flow capping functionality.
"""
import sys
import os
import time

# Add the backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from dummy_instrument import DummyInstrument

def test_extreme_values():
    print("=== Dummy Instrument Extreme Value Test ===")
    
    # Create a dummy instrument
    dummy = DummyInstrument(port="TEST", address=1)
    
    print(f"Instrument ID: {dummy.id}")
    print(f"Capacity: {dummy.readParameter(21)} {dummy.readParameter(129)}")
    
    # Set a normal setpoint
    dummy.writeParameter(206, 50.0)  # 50 ln/min setpoint
    print(f"Setpoint: {dummy.readParameter(206)} ln/min")
    
    print("\n--- Normal Measurements ---")
    for i in range(5):
        measure = dummy.readParameter(205)  # FMEASURE_DDE
        print(f"Measurement {i+1}: {measure:.3f}")
        time.sleep(0.1)
    
    print("\n--- Enabling Extreme Value Test ---")
    dummy.enable_extreme_test(enabled=True, interval=3)  # Every 3 measurements
    
    print("Taking measurements (should see extreme values)...")
    extreme_count = 0
    for i in range(10):
        measure = dummy.readParameter(205)  # FMEASURE_DDE
        if measure > 1000:  # Detect extreme values
            extreme_count += 1
            print(f"Measurement {i+1}: {measure:.1e} *** EXTREME VALUE ***")
        else:
            print(f"Measurement {i+1}: {measure:.3f}")
        time.sleep(0.1)
    
    print(f"\nDetected {extreme_count} extreme values")
    
    print("\n--- Disabling Extreme Value Test ---")
    dummy.enable_extreme_test(enabled=False)
    
    print("Taking final measurements (should be normal)...")
    for i in range(5):
        measure = dummy.readParameter(205)  # FMEASURE_DDE
        print(f"Final measurement {i+1}: {measure:.3f}")
        time.sleep(0.1)
    
    print("\n=== Test Complete ===")
    print("Now test in your main application:")
    print("1. Run the main FlowControl application")
    print("2. Open a meter or control dialog for a dummy instrument") 
    print("3. Enable extreme testing with: dummy_instrument.enable_extreme_test(True, 5)")
    print("4. Watch for 'Flow capped' warnings in the status display")
    print(f"5. Values above {dummy.readParameter(21) * 2:.1f} should be capped")

if __name__ == "__main__":
    test_extreme_values()