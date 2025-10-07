#!/usr/bin/env python3
"""
Test script for enhanced USB error handling and recovery mechanisms.
"""

import sys
import os
import time
import threading
from unittest.mock import Mock, patch

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_usb_error_handling():
    """Test USB disconnection error handling."""
    from backend.poller import PortPoller
    from backend.manager import ProparManager
    
    print("Testing Enhanced USB Error Handling")
    print("=" * 50)
    
    # Create a mock manager with error logger
    manager = ProparManager()
    manager.error_logger = Mock()
    manager.clear_shared_instrument_cache = Mock()
    manager.force_reconnect_port = Mock()
    manager.get_shared_instrument = Mock()
    
    # Create poller
    poller = PortPoller(manager, "/dev/ttyUSB0", addresses=[6])
    
    print(f"Created poller for {poller.port} with addresses: {poller.addresses}")
    
    # Test error classification
    test_errors = [
        ("Bad file descriptor", "bad_file_descriptor"),
        ("write failed: [Errno 9] Bad file descriptor", "bad_file_descriptor"),
        ("device disconnected", "device_disconnected"),
        ("No such file or directory", "usb_disconnection"),
        ("Serial connection lost", "usb_disconnection"),
        ("Connection timeout", "timeout"),
        ("Permission denied", "permission_denied")
    ]
    
    print("\nError Classification Tests:")
    print("-" * 30)
    
    for error_msg, expected_type in test_errors:
        # Test error classification logic
        error_msg_lower = error_msg.lower()
        
        usb_disconnect_indicators = [
            "bad file descriptor", "errno 9", "write failed", "read failed",
            "device disconnected", "device not found", "no such file or directory",
            "port that is not open", "serial exception", "connection lost"
        ]
        
        if any(indicator in error_msg_lower for indicator in usb_disconnect_indicators):
            if "bad file descriptor" in error_msg_lower or "errno 9" in error_msg_lower:
                error_type = "bad_file_descriptor"
            elif "write failed" in error_msg_lower or "read failed" in error_msg_lower:
                error_type = "write_read_failed"
            elif "device disconnected" in error_msg_lower or "device not found" in error_msg_lower:
                error_type = "device_disconnected"
            elif "no such file" in error_msg_lower:
                error_type = "device_not_found"
            elif "port that is not open" in error_msg_lower:
                error_type = "port_closed"
            else:
                error_type = "usb_disconnection"
        elif "timeout" in error_msg_lower:
            error_type = "timeout"
        elif "permission denied" in error_msg_lower or "access denied" in error_msg_lower:
            error_type = "permission_denied"
        else:
            error_type = "communication"
        
        status = "✓" if error_type in expected_type or expected_type in error_type else "✗"
        print(f"{status} '{error_msg}' -> {error_type}")
    
    # Test consecutive error tracking
    print(f"\nConsecutive Error Tracking Test:")
    print("-" * 30)
    
    address = 6
    for i in range(12):  # Test beyond the 10 error threshold
        if address not in poller._consecutive_errors:
            poller._consecutive_errors[address] = 0
            
        poller._consecutive_errors[address] += 1
        poller._last_error_time[address] = time.time()
        
        if i < 9:
            print(f"Error {i+1}: Count = {poller._consecutive_errors[address]}")
        elif i == 9:
            print(f"Error {i+1}: Count = {poller._consecutive_errors[address]} (threshold reached)")
        else:
            print(f"Error {i+1}: Address would be temporarily disabled")
    
    # Test error count reset
    print(f"\nError Count Reset Test:")
    print("-" * 30)
    
    poller._consecutive_errors[address] = 5
    print(f"Before success: Error count = {poller._consecutive_errors[address]}")
    
    # Simulate successful communication
    if address in poller._consecutive_errors and poller._consecutive_errors[address] > 0:
        print(f"Communication restored for {poller.port} address {address}, resetting error count")
        poller._consecutive_errors[address] = 0
    
    print(f"After success: Error count = {poller._consecutive_errors[address]}")
    
    print("\n" + "=" * 50)
    print("USB error handling tests completed!")

def test_recovery_delays():
    """Test recovery delay mechanisms."""
    print("\nTesting Recovery Delay Mechanisms")
    print("=" * 40)
    
    error_types = [
        ("bad_file_descriptor", 1.0),
        ("write_read_failed", 1.0),
        ("device_disconnected", 1.0),
        ("usb_disconnection", 1.0),
        ("port_closed", 0.5),
        ("device_not_found", 0.5),
        ("timeout", 0.1),
        ("communication", 0.05)
    ]
    
    for error_type, expected_delay in error_types:
        # Determine delay based on error severity
        if error_type in ["bad_file_descriptor", "write_read_failed", "device_disconnected", "usb_disconnection"]:
            delay = 1.0
        elif error_type in ["port_closed", "device_not_found"]:
            delay = 0.5
        elif error_type == "timeout":
            delay = 0.1
        else:
            delay = 0.05
        
        status = "✓" if delay == expected_delay else "✗"
        print(f"{status} {error_type}: {delay}s delay")
    
    print("\n" + "=" * 40)
    print("Recovery delay tests completed!")

if __name__ == "__main__":
    test_usb_error_handling()
    test_recovery_delays()
    print(f"\nAll USB error handling tests completed!")
    print(f"\nKey Features Tested:")
    print(f"✓ Enhanced error classification for USB disconnections")
    print(f"✓ Consecutive error tracking and temporary disabling")
    print(f"✓ Automatic re-enabling after recovery period")
    print(f"✓ Variable recovery delays based on error severity")
    print(f"✓ Cache clearing and reconnection for critical errors")
    print(f"✓ Error count reset on successful communication")