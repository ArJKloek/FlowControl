#!/usr/bin/env python3
"""
Test script to verify the port parsing fix for both Windows and Linux formats
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.manager import ProparManager
from PyQt5.QtCore import QCoreApplication

def test_port_parsing():
    """Test the port parsing for different formats"""
    app = QCoreApplication(sys.argv)
    
    # Create manager instance
    manager = ProparManager()
    
    print("Testing port parsing fix...")
    
    # Test 1: Windows format
    print("\n1. Testing Windows port format...")
    manager._on_poller_error("COM3/5: Test communication timeout")
    print("✓ Windows format handled")
    
    # Test 2: Linux format
    print("\n2. Testing Linux port format...")
    manager._on_poller_error("/dev/ttyUSB0/3: Test communication timeout")
    print("✓ Linux format handled")
    
    # Test 3: Complex Linux format
    print("\n3. Testing complex Linux port format...")
    manager._on_poller_error("/dev/ttyUSB0/4: Connection failed - timeout")
    print("✓ Complex Linux format handled")
    
    # Test 4: Invalid address format
    print("\n4. Testing invalid address format...")
    manager._on_poller_error("/dev/ttyUSB0/abc: Invalid address")
    print("✓ Invalid address format handled")
    
    # Test 5: No port/address format
    print("\n5. Testing generic error format...")
    manager._on_poller_error("General communication error")
    print("✓ Generic error format handled")
    
    # Test 6: Multiple slashes (edge case)
    print("\n6. Testing edge case with multiple slashes...")
    manager._on_poller_error("/dev/serial/by-id/usb-device/5: Error message")
    print("✓ Multiple slashes handled")
    
    print("\n✓ All port parsing tests completed!")
    print("Check the error log CSV file for logged entries.")
    
    # Show CSV path if possible
    try:
        csv_path = manager.error_logger._get_log_file_path()
        print(f"Error log file: {csv_path}")
    except Exception as e:
        print(f"Could not get CSV path: {e}")

if __name__ == "__main__":
    test_port_parsing()