#!/usr/bin/env python3
"""
Debug script to investigate instrument 4 parameter reading issues.
"""

import sys
import time
from propar_new import master as ProparMaster
from backend.scanner import _read_dde_stable

def debug_instrument_4():
    """Debug instrument 4 parameter reading."""
    print("=== Debugging Instrument 4 ===")
    
    # Try to find instrument 4 on available ports
    ports_to_try = [
        'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'COM10'
    ]
    
    for port in ports_to_try:
        print(f"\nTrying port {port}...")
        try:
            m = ProparMaster(port, baudrate=38400)
            nodes = m.get_nodes()
            print(f"Found {len(nodes)} nodes on {port}")
            
            for node in nodes:
                address = int(node['address'])
                print(f"\nNode address: {address}")
                
                if address == 4:
                    print("=== FOUND INSTRUMENT 4 ===")
                    
                    # Test individual parameter reads
                    test_params = [115, 25, 21, 129, 24, 206, 91, 175]
                    param_names = {
                        115: "usertag", 25: "fluid", 21: "capacity", 
                        129: "unit", 24: "fluid_index", 206: "fsetpoint", 
                        91: "model", 175: "device_type"
                    }
                    
                    print("\nTesting individual parameter reads:")
                    for param in test_params:
                        try:
                            vals = _read_dde_stable(m, address, [param], debug=True)
                            value = vals.get(param)
                            print(f"  {param_names[param]} ({param}): {value}")
                        except Exception as e:
                            print(f"  {param_names[param]} ({param}): ERROR - {e}")
                    
                    print("\nTesting batch read:")
                    try:
                        vals = _read_dde_stable(m, address, test_params, debug=True)
                        for param in test_params:
                            value = vals.get(param)
                            print(f"  {param_names[param]} ({param}): {value}")
                    except Exception as e:
                        print(f"  Batch read ERROR: {e}")
                    
                    return  # Found and tested instrument 4
                        
        except Exception as e:
            print(f"  Error on {port}: {e}")
    
    print("\nInstrument 4 not found on any port.")

if __name__ == "__main__":
    debug_instrument_4()