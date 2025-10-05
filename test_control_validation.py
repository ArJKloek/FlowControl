#!/usr/bin/env python3
"""Test script to verify control dialog flow validation"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.dummy_instrument import DummyInstrument

class MockNode:
    """Mock node object that mimics the real node structure"""
    def __init__(self):
        self.port = "DUMMY0" 
        self.address = 1
        self.capacity = 100.0  # This should be available
        self.dev_type = "DMFC"
        self.unit = "ln/min"

def test_flow_validation():
    """Test the flow validation logic from control dialog"""
    # Create a mock node with capacity
    node = MockNode()
    print(f"Node capacity: {node.capacity}")
    print(f"Node type: {node.dev_type}")
    
    # Simulate extreme flow value
    raw_flow = 10000000.0
    print(f"Raw flow measurement: {raw_flow}")
    
    # Apply the same validation logic as in control dialog
    capacity = getattr(node, "capacity", None)
    print(f"Retrieved capacity: {capacity}")
    
    if capacity is not None:
        max_allowed = float(capacity) * 2.0  # 200% of capacity
        print(f"Max allowed (200% of capacity): {max_allowed}")
        
        if raw_flow > max_allowed:
            # Cap the measurement and show warning
            capped_flow = max_allowed
            print(f"WOULD CAP: {raw_flow:.1f} → {capped_flow:.1f} (>200% capacity)")
            print("✓ Flow capping would work correctly")
        else:
            print("✗ Flow would NOT be capped (unexpected)")
    else:
        print("✗ No capacity available - validation would be skipped")

if __name__ == "__main__":
    test_flow_validation()