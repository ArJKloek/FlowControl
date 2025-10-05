#!/usr/bin/env python3
"""
Test script to debug extreme value warnings.
This script will help identify why warnings aren't appearing.
"""
import os
import sys
import time

# Set up dummy mode
os.environ["FLOWCONTROL_USE_DUMMY"] = "1"
print("Environment set for dummy instruments")

# Add the current directory to path to import backend modules
sys.path.insert(0, os.getcwd())

print("Testing extreme value warning system...")
print("1. Testing the warning logic...")

def test_warning_display():
    """Test if the warning logic works correctly."""
    print("\n=== Testing Warning Logic ===")
    
    # Test parameters (matching what the real system would have)
    test_cases = [
        {"capacity": 100.0, "measurement": 50.0, "should_warn": False},
        {"capacity": 100.0, "measurement": 200.0, "should_warn": False},  # At 200% limit
        {"capacity": 100.0, "measurement": 250.0, "should_warn": True},   # Above 200% limit
        {"capacity": 100.0, "measurement": 1.0e7, "should_warn": True},   # Extreme value
    ]
    
    for i, case in enumerate(test_cases, 1):
        capacity = case["capacity"]
        measurement = case["measurement"]
        should_warn = case["should_warn"]
        
        max_allowed = capacity * 2.0
        will_warn = measurement > max_allowed
        
        print(f"Test {i}:")
        print(f"  Capacity: {capacity}")
        print(f"  Measurement: {measurement}")
        print(f"  Max allowed (200%): {max_allowed}")
        print(f"  Expected warning: {should_warn}")
        print(f"  Logic produces warning: {will_warn}")
        print(f"  Result: {'✓ PASS' if will_warn == should_warn else '✗ FAIL'}")
        print()

def test_steps_to_see_warnings():
    """Print steps the user should follow to see warnings."""
    print("\n=== Steps to See Warnings ===")
    print("To see extreme value warnings in the application:")
    print("1. Start the application with: python main.py --dummy --extreme")
    print("2. Wait for the message 'Extreme value testing will be enabled after startup'")
    print("3. Open the Scanner (from menu)")
    print("4. Wait for dummy instruments to appear in the scanner")
    print("5. Double-click on a dummy instrument (DUMMY, DUMMY2, or DUMMY_METER)")
    print("6. This opens the meter dialog where warnings will appear")
    print("7. Wait for extreme values to be generated (every 3 measurements now)")
    print("8. Warnings should appear in the status line at the bottom of the meter dialog")
    print("9. Warnings are orange/red text that say 'Flow capped: X → Y (>200% capacity)'")
    print()
    print("If you still don't see warnings, check:")
    print("- Console output for debug messages starting with '[MeterDialog]'")
    print("- That the instrument has a capacity set (should show in meter dialog)")
    print("- That extreme values are being generated (console messages)")

if __name__ == "__main__":
    test_warning_display()
    test_steps_to_see_warnings()