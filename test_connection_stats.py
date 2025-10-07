#!/usr/bin/env python3
"""
Test script for connection stability monitoring features.
Tests the new connection statistics tracking in PortPoller.
"""

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.poller import PortPoller

def test_connection_stats():
    """Test connection statistics tracking."""
    print("Testing connection statistics tracking...")
    
    # Create a test poller (manager can be None for testing)
    poller = PortPoller(None, "TEST_PORT", addresses=[1])
    
    # Check initial stats
    print("\n1. Initial statistics:")
    stats = poller.get_connection_stats()
    print(f"   Port: {stats['port']}")
    print(f"   Recoveries: {stats['connection_recoveries']}")
    print(f"   Uptime: {stats['uptime_seconds']:.1f}s")
    print(f"   Consecutive errors: {stats['consecutive_errors']}")
    
    # Test connection summary
    print("\n2. Connection summary:")
    poller.print_connection_summary()
    
    # Simulate some connection activity
    print("\n3. Simulating connection recovery...")
    poller._connection_recoveries[1] = 2  # Address 1 had 2 recoveries
    poller._last_recovery_time = time.time()
    poller._consecutive_errors[1] = 0
    
    print("   Updated statistics:")
    poller.print_connection_summary()
    
    # Simulate errors
    print("\n4. Simulating consecutive errors...")
    poller._consecutive_errors[1] = 3  # Address 1 has 3 consecutive errors
    poller._last_error_time = time.time()
    
    stats = poller.get_connection_stats()
    print(f"   Consecutive errors: {stats['consecutive_errors']}")
    if stats['last_error_time']:
        print(f"   Last error: {time.strftime('%H:%M:%S', time.localtime(stats['last_error_time']))}")
    
    print("\n✓ Connection statistics tracking test completed successfully!")

if __name__ == "__main__":
    test_connection_stats()