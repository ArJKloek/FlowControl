#!/usr/bin/env python3
"""
Test script to verify that capacity validation only applies to DMFC instruments.
Tests that DMFM, DLFC, DLFM and other devices bypass the validation.
"""

import time

def simulate_dmfc_only_validation(fmeasure, capacity, ident_nr):
    """Simulate the DMFC-only validation logic"""
    
    # Get values for validation
    fmeasure_value = fmeasure
    capacity_value = capacity
    
    # Validate FMEASURE against CAPACITY (skip if > 150% of capacity)
    # Only apply validation to DMFC instruments (ident_nr == 7)
    skip_measurement = False
    capacity_150_percent = None
    
    if (ident_nr == 7 and  # Only for DMFC instruments
        capacity_value is not None and fmeasure_value is not None):
        try:
            capacity_150_percent = float(capacity_value) * 1.5
            if float(fmeasure_value) > capacity_150_percent:
                skip_measurement = True
                print(f"⚠️  COM1/3: DMFC validation - Skipping measurement - FMEASURE ({fmeasure_value:.3f}) exceeds 150% of capacity ({capacity_150_percent:.3f})")
        except (ValueError, TypeError):
            # If conversion fails, continue with measurement
            pass
    
    # Determine device category based on identification number
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
    
    if skip_measurement:
        # Return telemetry data for skipped measurement
        telemetry_data = {
            "ts": time.time(), 
            "port": "COM1", 
            "address": 3,
            "kind": "validation_skip", 
            "name": "dmfc_capacity_exceeded", 
            "value": float(fmeasure_value),
            "capacity": float(capacity_value),
            "threshold": capacity_150_percent,
            "device_type": "DMFC",
            "reason": f"DMFC validation: FMEASURE ({fmeasure_value:.3f}) > 150% capacity ({capacity_150_percent:.3f})"
        }
        return "SKIPPED", telemetry_data, device_category
    else:
        # Return normal measurement data
        measured_data = {
            "port": "COM1",
            "address": 3,
            "data": {
                "fmeasure": float(fmeasure_value) if fmeasure_value is not None else 0.0,
                "capacity": capacity_value,
                "device_category": device_category,
                "ident_nr": ident_nr,
            },
            "ts": time.time(),
        }
        return "MEASURED", measured_data, device_category

def test_dmfc_only_validation():
    """Test that validation only applies to DMFC instruments"""
    
    print("🔍 DMFC-Only Capacity Validation Test")
    print("=" * 90)
    print(f"{'Device':<6} {'Type':<5} {'FMEASURE':<10} {'CAPACITY':<10} {'150% Cap':<10} {'Action':<10} {'Reason':<30}")
    print("-" * 90)
    
    # Test scenarios: (ident_nr, device_name, fmeasure, capacity, description)
    test_scenarios = [
        # DMFC tests (should apply validation)
        (7, "DMFC", 25.0, 20.0, "Normal DMFC - should pass"),
        (7, "DMFC", 30.0, 20.0, "DMFC at 150% - should pass"),
        (7, "DMFC", 30.1, 20.0, "DMFC over 150% - should SKIP"),
        (7, "DMFC", 50.0, 20.0, "DMFC spike - should SKIP"),
        
        # DMFM tests (should bypass validation)
        (8, "DMFM", 25.0, 20.0, "Normal DMFM - should pass"),
        (8, "DMFM", 30.1, 20.0, "DMFM over 150% - should PASS (no validation)"),
        (8, "DMFM", 100.0, 20.0, "DMFM huge spike - should PASS (no validation)"),
        
        # Other device types (should bypass validation)
        (12, "DLFC", 30.1, 20.0, "DLFC over 150% - should PASS (no validation)"),
        (13, "DLFM", 50.0, 20.0, "DLFM over 150% - should PASS (no validation)"),
        (9, "DEPC", 40.0, 20.0, "DEPC over 150% - should PASS (no validation)"),
        (10, "DEPM", 60.0, 20.0, "DEPM over 150% - should PASS (no validation)"),
        
        # Edge cases
        (7, "DMFC", None, 20.0, "DMFC no fmeasure - should pass"),
        (7, "DMFC", 30.1, None, "DMFC no capacity - should pass"),
        (99, "UNK", 50.0, 20.0, "Unknown device - should pass"),
    ]
    
    for ident_nr, device_name, fmeasure, capacity, description in test_scenarios:
        try:
            result, data, device_category = simulate_dmfc_only_validation(fmeasure, capacity, ident_nr)
            
            # Format display values
            fmeasure_str = f"{fmeasure:.1f}" if fmeasure is not None else "None"
            capacity_str = f"{capacity:.1f}" if capacity is not None else "None"
            
            if result == "SKIPPED":
                threshold = data.get('threshold', 0)
                cap_150_str = f"{threshold:.1f}"
                action = "SKIP"
                reason = "DMFC validation triggered"
                
            else:
                if capacity is not None:
                    cap_150_str = f"{float(capacity) * 1.5:.1f}"
                else:
                    cap_150_str = "N/A"
                action = "PASS"
                if ident_nr == 7:
                    reason = "DMFC within limits"
                else:
                    reason = "Non-DMFC (validation bypassed)"
            
            # Check if result matches expectation
            expected_skip = (ident_nr == 7 and fmeasure is not None and capacity is not None and fmeasure > capacity * 1.5)
            status = "✅" if (result == "SKIPPED") == expected_skip else "❌"
            
            print(f"{device_name:<6} {ident_nr:<5} {fmeasure_str:<10} {capacity_str:<10} {cap_150_str:<10} {action:<10} {reason:<30} {status}")
            
        except Exception as e:
            print(f"{device_name:<6} {ident_nr:<5} {fmeasure_str:<10} {capacity_str:<10} {'ERROR':<10} {'ERROR':<10} {str(e):<30} ❌")
    
    print("\n" + "=" * 90)
    print("📋 Validation Rules:")
    print("   ✅ DMFC (ID=7): Apply 150% capacity validation")
    print("   ✅ DMFM (ID=8): Bypass validation (measurement only)")
    print("   ✅ DLFC (ID=12): Bypass validation") 
    print("   ✅ DLFM (ID=13): Bypass validation")
    print("   ✅ DEPC (ID=9): Bypass validation")
    print("   ✅ DEPM (ID=10): Bypass validation")
    print("   ✅ Other devices: Bypass validation")
    
    print("\n💡 Rationale:")
    print("   • DMFC = Controllers can be regulated, validation prevents overrange")
    print("   • DMFM = Meters are read-only, let them report actual values")
    print("   • Other devices = Different physics, different validation needs")

if __name__ == "__main__":
    test_dmfc_only_validation()