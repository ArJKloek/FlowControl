#!/usr/bin/env python3
"""
Test script to verify address validation fixes.
"""

import sys
import os

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_address_validation():
    """Test address validation in PortPoller."""
    from backend.poller import PortPoller
    from backend.manager import ProparManager
    
    print("Testing Address Validation Fixes")
    print("=" * 40)
    
    # Create a mock manager
    manager = ProparManager()
    
    # Test 1: Valid single address
    print("Test 1: Valid single address (5)")
    try:
        poller = PortPoller(manager, "/dev/ttyUSB0", addresses=5)
        print(f"✓ Success: {poller.addresses}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Test 2: Valid multiple addresses
    print("\nTest 2: Valid multiple addresses [1, 2, 3]")
    try:
        poller = PortPoller(manager, "/dev/ttyUSB0", addresses=[1, 2, 3])
        print(f"✓ Success: {poller.addresses}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Test 3: Invalid address (out of range)
    print("\nTest 3: Invalid address (300 - out of range)")
    try:
        poller = PortPoller(manager, "/dev/ttyUSB0", addresses=300)
        print(f"Result: {poller.addresses}")
    except Exception as e:
        print(f"Error (expected): {e}")
    
    # Test 4: Invalid address format (string)
    print("\nTest 4: Invalid address format ('abc')")
    try:
        poller = PortPoller(manager, "/dev/ttyUSB0", addresses="abc")
        print(f"Result: {poller.addresses}")
    except Exception as e:
        print(f"Error (expected): {e}")
    
    # Test 5: Mixed valid/invalid addresses
    print("\nTest 5: Mixed valid/invalid addresses [1, 'abc', 300, 2]")
    try:
        poller = PortPoller(manager, "/dev/ttyUSB0", addresses=[1, "abc", 300, 2])
        print(f"Result (should contain only 1, 2): {poller.addresses}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 6: add_node with invalid address
    print("\nTest 6: add_node with invalid address")
    try:
        poller = PortPoller(manager, "/dev/ttyUSB0")
        poller.add_node("invalid")
        poller.add_node(500)
        poller.add_node(1)  # This should work
        print(f"Result (should contain only 1): {poller.addresses}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "=" * 40)
    print("Address validation tests completed!")

def test_manager_validation():
    """Test address validation in Manager."""
    from backend.manager import ProparManager
    
    print("\nTesting Manager Address Validation")
    print("=" * 40)
    
    manager = ProparManager()
    
    # Test valid address
    print("Test: get_shared_instrument with valid address (5)")
    try:
        # This will fail because port doesn't exist, but should validate address first
        inst = manager.get_shared_instrument("/dev/ttyUSB0", 5)
        print("✓ Address validation passed")
    except ValueError as e:
        if "Invalid address" in str(e):
            print(f"✗ Address validation failed: {e}")
        else:
            print("✓ Address validation passed (port error expected)")
    except Exception as e:
        print("✓ Address validation passed (connection error expected)")
    
    # Test invalid address
    print("\nTest: get_shared_instrument with invalid address (300)")
    try:
        inst = manager.get_shared_instrument("/dev/ttyUSB0", 300)
        print("✗ Address validation failed - should have rejected 300")
    except ValueError as e:
        if "Invalid address" in str(e) or "out of valid range" in str(e):
            print(f"✓ Address validation worked: {e}")
        else:
            print(f"? Unexpected validation error: {e}")
    except Exception as e:
        print(f"? Unexpected error: {e}")
    
    print("\n" + "=" * 40)
    print("Manager validation tests completed!")

if __name__ == "__main__":
    test_address_validation()
    test_manager_validation()
    print("\nAll tests completed!")