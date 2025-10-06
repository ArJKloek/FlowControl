#!/usr/bin/env python3
"""
Test script to verify device type detection using parameter 175.
This will help you identify if your instruments are DMFC or DMFM.
"""

import time

def test_device_type_detection():
    """Test the device type detection logic"""
    
    # Test cases based on the propar parameters database
    test_cases = [
        (7, "DMFC", "Digital Mass Flow Controller"),
        (8, "DMFM", "Digital Mass Flow Meter"),
        (12, "DLFC", "Digital Liquid Flow Controller"),
        (13, "DLFM", "Digital Liquid Flow Meter"),
        (9, "DEPC", "Digital Electronic Pressure Controller"),
        (10, "DEPM", "Digital Electronic Pressure Meter"),
        (1, "UNKNOWN", "RS232/FLOW-BUS interface"),
        (99, "UNKNOWN", "Unknown device type"),
    ]
    
    print("🔍 Device Type Detection Test")
    print("=" * 50)
    print(f"{'ID':<3} {'Category':<8} {'Description':<35}")
    print("-" * 50)
    
    for ident_nr, expected_category, description in test_cases:
        # Device type detection logic (same as in poller)
        device_category = "UNKNOWN"
        if ident_nr == 7:
            device_category = "DMFC"  # Digital Mass Flow Controller
        elif ident_nr == 8:
            device_category = "DMFM"  # Digital Mass Flow Meter
        elif ident_nr == 12:
            device_category = "DLFC"  # Digital Liquid Flow Controller  
        elif ident_nr == 13:
            device_category = "DLFM"  # Digital Liquid Flow Meter
        elif ident_nr == 9:
            device_category = "DEPC"  # Digital Electronic Pressure Controller
        elif ident_nr == 10:
            device_category = "DEPM"  # Digital Electronic Pressure Meter
        
        status = "✅" if device_category == expected_category else "❌"
        print(f"{ident_nr:<3} {device_category:<8} {description:<35} {status}")
    
    print("\n" + "=" * 50)
    print("📋 Parameter 175 (IDENT_NR_DDE) Value Meanings:")
    print("   7  = DMFC (Digital Mass Flow Controller)")
    print("   8  = DMFM (Digital Mass Flow Meter)")
    print("   9  = DEPC (Digital Electronic Pressure Controller)")
    print("   10 = DEPM (Digital Electronic Pressure Meter)")
    print("   12 = DLFC (Digital Liquid Flow Controller)")
    print("   13 = DLFM (Digital Liquid Flow Meter)")
    print("\n💡 Key Difference:")
    print("   DMFC (7) = Controller (can control flow)")
    print("   DMFM (8) = Meter (measurement only)")
    print("   Look for the parameter 175 value in your debug output!")

if __name__ == "__main__":
    test_device_type_detection()