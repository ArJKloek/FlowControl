#!/usr/bin/env python3
"""
Test script to verify extreme value warnings are working correctly.
Simple version that tests just the warning logic.
"""
import time

def test_flow_validation():
    """Test the flow validation logic that should show warnings."""
    print("Testing flow validation logic...")
    
    # Simulate instrument capacity
    capacity = 10.0
    max_allowed = capacity * 2.0  # 200% capacity limit
    
    print(f"Instrument capacity: {capacity}")
    print(f"200% capacity limit: {max_allowed}")
    print()
    
    # Test various measurements
    test_measurements = [
        5.0,      # Normal
        10.0,     # At capacity
        15.0,     # 150% capacity
        20.0,     # At 200% limit
        25.0,     # Above limit - should warn
        100.0,    # Way above limit - should warn
        1.0e7,    # Extreme value like instrument error - should warn
    ]
    
    for measurement in test_measurements:
        print(f"Measurement: {measurement:.1f}")
        
        if measurement > max_allowed:
            capped_flow = max_allowed
            print(f"  WARNING: Flow capped: {measurement:.1f} → {capped_flow:.1f} (>200% capacity)")
        else:
            print(f"  Normal: within 200% capacity limit")
        
        print()

def test_extreme_value_generation():
    """Test the extreme value generation pattern."""
    print("Testing extreme value generation pattern...")
    
    # Simulate the extreme testing logic
    extreme_test_enabled = True
    extreme_test_interval = 5  # Every 5 measurements
    extreme_test_counter = 0
    
    for i in range(15):
        extreme_test_counter += 1
        
        if extreme_test_enabled and extreme_test_counter >= extreme_test_interval:
            extreme_test_counter = 0
            measurement = 1.0e7  # Extreme value
            print(f"Measurement {i+1}: {measurement:.1e} (EXTREME TEST VALUE)")
        else:
            measurement = 5.0 + (i % 3)  # Normal values
            print(f"Measurement {i+1}: {measurement:.1f} (normal)")

if __name__ == "__main__":
    test_flow_validation()
    print("\n" + "="*50 + "\n")
    test_extreme_value_generation()