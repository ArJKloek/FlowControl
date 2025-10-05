#!/usr/bin/env python3
"""
Test script to verify extreme value warnings are working correctly.
"""
import os
import time
import sys

# Enable dummy instruments
os.environ["FLOWCONTROL_USE_DUMMY"] = "1"

from backend.dummy_instrument import DummyInstrument
from backend.models import Node

def test_extreme_values():
    """Test that extreme values are generated and detected."""
    print("Testing extreme value generation and warnings...")
    
    # Create a dummy instrument
    dummy = DummyInstrument("dummy_CO2", 1)
    dummy._capacity = 10.0  # Set capacity to 10.0
    
    # Enable extreme testing - every 3 measurements for faster testing
    dummy.enable_extreme_test(True, 3)
    print(f"Extreme testing enabled: interval={dummy._extreme_test_interval}")
    
    # Create a node to simulate what the dialogs would see
    node = Node("dummy_CO2", 1)
    node.capacity = 10.0
    
    print(f"Node capacity: {node.capacity}")
    print(f"200% capacity limit: {float(node.capacity) * 2.0}")
    
    # Test measurements
    for i in range(10):
        measurement = dummy.readParameter(69)  # FMEASURE_DDE
        print(f"Measurement {i+1}: {measurement:.2f}")
        
        # Check if this would trigger a warning (>200% capacity)
        capacity = float(node.capacity)
        max_allowed = capacity * 2.0
        if measurement > max_allowed:
            print(f"  WARNING: Flow {measurement:.1f} > {max_allowed:.1f} (200% capacity)")
            print(f"  Would be capped to: {max_allowed:.1f}")
        else:
            print(f"  Normal flow within limits")
        
        time.sleep(0.2)  # Small delay to allow measurements to update
    
    print("\nTest completed.")

if __name__ == "__main__":
    test_extreme_values()