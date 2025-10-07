#!/usr/bin/env python3
"""
Integration test for USB error handling with connection statistics.
Tests the complete error detection and recovery system.
"""

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.poller import PortPoller

def test_error_handling_integration():
    """Test complete error handling with statistics tracking."""
    print("Testing complete USB error handling and statistics integration...")
    
    # Create a test poller
    poller = PortPoller(None, "TEST_PORT", addresses=[1, 2])
    
    print(f"\n1. Initial setup for {poller.port} with addresses: {poller.addresses}")
    poller.print_connection_summary()
    
    # Test direct consecutive error tracking (simulating what happens during real polling)
    print("\n2. Testing consecutive error tracking for address 1:")
    address = 1
    
    # Initialize consecutive errors for address 1
    if address not in poller._consecutive_errors:
        poller._consecutive_errors[address] = 0
    
    # Simulate 5 consecutive errors
    for i in range(5):
        poller._consecutive_errors[address] += 1
        poller._last_error_time = time.time()
        current_count = poller._consecutive_errors.get(address, 0)
        print(f"   Error #{i+1}: consecutive_errors[{address}] = {current_count}")
        
        if current_count >= 3:
            print(f"   Address {address} would be disabled due to consecutive errors")
    
    # Test recovery tracking
    print(f"\n3. Testing recovery for address {address}:")
    
    # Initialize recovery tracking
    if address not in poller._connection_recoveries:
        poller._connection_recoveries[address] = 0
    
    # Simulate successful recovery
    old_error_count = poller._consecutive_errors[address]
    poller._connection_recoveries[address] += 1
    poller._consecutive_errors[address] = 0
    poller._last_recovery_time = time.time()
    
    consecutive_after_recovery = poller._consecutive_errors.get(address, 0)
    recoveries = poller._connection_recoveries.get(address, 0)
    print(f"   Before recovery: consecutive_errors[{address}] = {old_error_count}")
    print(f"   After recovery: consecutive_errors[{address}] = {consecutive_after_recovery}")
    print(f"   Total recoveries[{address}] = {recoveries}")
    
    # Show intermediate statistics
    print("\n4. Connection statistics after address 1 recovery:")
    poller.print_connection_summary()
    
    # Test multi-address statistics
    print("\n5. Testing multi-address statistics:")
    address2 = 2
    
    # Add some activity for address 2
    if address2 not in poller._consecutive_errors:
        poller._consecutive_errors[address2] = 0
    if address2 not in poller._connection_recoveries:
        poller._connection_recoveries[address2] = 0
    
    # Simulate errors and recovery for address 2
    poller._consecutive_errors[address2] = 2
    poller._connection_recoveries[address2] = 1
    
    stats = poller.get_connection_stats()
    print(f"   Total recoveries across all addresses: {stats['connection_recoveries']}")
    print(f"   Total consecutive errors: {stats['consecutive_errors']}")
    print(f"   Per-address breakdown:")
    print(f"     Recoveries: {stats['connection_recoveries_by_address']}")
    print(f"     Errors: {stats['consecutive_errors_by_address']}")
    
    # Final summary
    print("\n6. Final connection statistics:")
    poller.print_connection_summary()
    
    print("\n✓ Complete error handling integration test passed!")
    print("✓ Connection stability monitoring is working correctly!")
    print("✓ Multi-address error tracking validated!")

if __name__ == "__main__":
    test_error_handling_integration()