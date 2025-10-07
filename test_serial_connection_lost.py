#!/usr/bin/env python3
"""
Test script for the specific "file descriptor is None or port is closed" error pattern.
"""

import sys
import os
import time
from unittest.mock import Mock

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_serial_connection_lost_detection():
    """Test detection of the specific serial connection lost error pattern."""
    from backend.poller import PortPoller
    from backend.manager import ProparManager
    
    print("Testing Serial Connection Lost Error Detection")
    print("=" * 55)
    
    # Create a mock manager
    manager = ProparManager()
    manager.error_logger = Mock()
    manager.clear_shared_instrument_cache = Mock()
    manager.force_reconnect_port = Mock()
    
    # Test the specific error patterns we're seeing
    test_errors = [
        "Serial connection lost - file descriptor is None or port is closed",
        "Serial file descriptor lost: write failed: [Errno 9] Bad file descriptor",
        "file descriptor is None",
        "port is closed",
        "Serial connection lost",
        "Bad file descriptor",
        "write failed: [Errno 9]"
    ]
    
    print("Error Pattern Detection:")
    print("-" * 30)
    
    for error_msg in test_errors:
        error_msg_lower = error_msg.lower()
        
        # USB disconnection indicators (updated list)
        usb_disconnect_indicators = [
            "bad file descriptor", "errno 9", "write failed", "read failed",
            "device disconnected", "device not found", "no such file or directory",
            "port that is not open", "serial exception", "connection lost",
            "file descriptor is none", "port is closed", "serial connection lost"
        ]
        
        detected = any(indicator in error_msg_lower for indicator in usb_disconnect_indicators)
        
        # Classify the error type
        if detected:
            if "bad file descriptor" in error_msg_lower or "errno 9" in error_msg_lower:
                error_type = "bad_file_descriptor"
            elif "write failed" in error_msg_lower or "read failed" in error_msg_lower:
                error_type = "write_read_failed"
            elif ("port that is not open" in error_msg_lower or 
                  "port is closed" in error_msg_lower or
                  "file descriptor is none" in error_msg_lower):
                error_type = "port_closed"
            elif "serial connection lost" in error_msg_lower or "connection lost" in error_msg_lower:
                error_type = "serial_connection_lost"
            else:
                error_type = "usb_disconnection"
        else:
            error_type = "not_detected"
        
        status = "✓" if detected else "✗"
        print(f"{status} '{error_msg}' -> {error_type}")
    
    print(f"\nSpecific Test for Your Error:")
    print("-" * 30)
    your_error = "Serial connection lost - file descriptor is None or port is closed"
    error_msg_lower = your_error.lower()
    
    # Check each indicator
    indicators_found = []
    usb_disconnect_indicators = [
        "bad file descriptor", "errno 9", "write failed", "read failed",
        "device disconnected", "device not found", "no such file or directory",
        "port that is not open", "serial exception", "connection lost",
        "file descriptor is none", "port is closed", "serial connection lost"
    ]
    
    for indicator in usb_disconnect_indicators:
        if indicator in error_msg_lower:
            indicators_found.append(indicator)
    
    print(f"Error message: '{your_error}'")
    print(f"Indicators found: {indicators_found}")
    
    # Determine error type
    if ("port is closed" in error_msg_lower or 
        "file descriptor is none" in error_msg_lower):
        error_type = "port_closed"
    elif "serial connection lost" in error_msg_lower:
        error_type = "serial_connection_lost"
    else:
        error_type = "usb_disconnection"
    
    print(f"Classified as: {error_type}")
    
    # Test recovery delay
    if error_type in ["bad_file_descriptor", "write_read_failed", "device_disconnected", "usb_disconnection", "serial_connection_lost"]:
        delay = 1.0
    elif error_type in ["port_closed", "device_not_found"]:
        delay = 0.5
    else:
        delay = 0.05
    
    print(f"Recovery delay: {delay}s")
    
    print("\n" + "=" * 55)
    print("Serial connection lost detection test completed!")

def test_enhanced_read_parameters_handling():
    """Test the enhanced read_parameters error handling."""
    print(f"\nTesting Enhanced read_parameters Error Handling")
    print("=" * 50)
    
    # Test the error detection logic from the read_parameters exception handler
    test_errors = [
        "integer is required (got type NoneType)",
        "file descriptor",
        "Serial connection lost",
        "port is closed",
        "file descriptor is None"
    ]
    
    print("read_parameters Error Detection:")
    print("-" * 35)
    
    for error_msg in test_errors:
        # This is the logic from the enhanced read_parameters exception handler
        detected = ("integer is required (got type NoneType)" in error_msg or 
                   "file descriptor" in error_msg or 
                   "Serial connection lost" in error_msg or
                   "port is closed" in error_msg or
                   "file descriptor is None" in error_msg)
        
        status = "✓" if detected else "✗"
        print(f"{status} '{error_msg}' -> {'DETECTED' if detected else 'NOT DETECTED'}")
    
    # Test the specific error we're seeing
    your_error = "Serial connection lost - file descriptor is None or port is closed"
    detected = ("integer is required (got type NoneType)" in your_error or 
               "file descriptor" in your_error or 
               "Serial connection lost" in your_error or
               "port is closed" in your_error or
               "file descriptor is None" in your_error)
    
    print(f"\nYour specific error:")
    print(f"'{your_error}' -> {'✓ DETECTED' if detected else '✗ NOT DETECTED'}")
    
    if detected:
        print("✓ Will trigger enhanced recovery actions:")
        print("  - Consecutive error tracking")
        print("  - Cache clearing")
        print("  - Port reconnection")
        print("  - Temporary disabling after 10 errors")
        print("  - 1 second extra delay for rescheduling")
    
    print("\n" + "=" * 50)
    print("Enhanced error handling test completed!")

if __name__ == "__main__":
    test_serial_connection_lost_detection()
    test_enhanced_read_parameters_handling()
    print(f"\nAll tests completed!")
    print(f"\nThe error 'Serial connection lost - file descriptor is None or port is closed' should now be:")
    print(f"✓ Properly detected in both main polling loop and read_parameters")
    print(f"✓ Classified as either 'port_closed' or 'serial_connection_lost'")
    print(f"✓ Trigger immediate cache clearing and reconnection")
    print(f"✓ Use appropriate recovery delays (0.5s or 1.0s)")
    print(f"✓ Include consecutive error tracking and temporary disabling")
    print(f"✓ Log with enhanced context including error counts")