#!/usr/bin/env python3
"""
Simple Manual FlowControl Instrument Test
For use with actual hardware on /dev/ttyUSB0 with addresses 3, 5, 6
"""

import time
import sys
import os
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.thread_safe_propar import ThreadSafeProparInstrument

# DDE Parameter definitions
FSETPOINT_DDE = 206     # fSetpoint (float)
FMEASURE_DDE = 205      # fMeasure (float)
CAPACITY_DDE = 21       # capacity (float)
TYPE_DDE = 90           # type (string)
USERTAG_DDE = 115       # usertag (string)


def test_instrument_connection(port, address):
    """Test connection to a single instrument"""
    print(f"\n🔧 Testing instrument at address {address}...")
    
    try:
        # Create instrument instance
        instrument = ThreadSafeProparInstrument(port, address=address)
        
        # Test basic parameters
        device_type = instrument.readParameter(TYPE_DDE)
        capacity = instrument.readParameter(CAPACITY_DDE)
        usertag = instrument.readParameter(USERTAG_DDE)
        
        print(f"✅ Address {address}: Connection successful!")
        print(f"   📋 Device Type: {device_type}")
        print(f"   📊 Capacity: {capacity}")
        print(f"   🏷️  User Tag: {usertag}")
        
        return instrument, True
        
    except Exception as e:
        print(f"❌ Address {address}: Connection failed!")
        print(f"   ⚠️  Error: {e}")
        return None, False


def test_continuous_measurements(instruments, addresses, duration=10):
    """Test continuous measurements from connected instruments"""
    print(f"\n🚀 Starting {duration}-second measurement test...")
    print("-" * 80)
    
    start_time = time.time()
    cycle = 0
    
    while (time.time() - start_time) < duration:
        cycle += 1
        cycle_start = time.perf_counter()
        
        print(f"Cycle {cycle:3d}: ", end="")
        
        for address in addresses:
            if address in instruments:
                try:
                    # Read measurement
                    fmeasure = instruments[address].readParameter(FMEASURE_DDE)
                    fsetpoint = instruments[address].readParameter(FSETPOINT_DDE)
                    
                    # Display result
                    if isinstance(fmeasure, (int, float)):
                        print(f"Addr{address}:{fmeasure:>8.2f}({fsetpoint:>6.2f})", end=" ")
                    else:
                        print(f"Addr{address}:{'N/A':>8}({'N/A':>6})", end=" ")
                        
                except Exception as e:
                    error_msg = str(e)[:12]
                    print(f"Addr{address}:{'ERROR':>8}({error_msg})", end=" ")
            else:
                print(f"Addr{address}:{'DISC':>8}({'----':>6})", end=" ")
        
        # Calculate cycle time
        cycle_time = (time.perf_counter() - cycle_start) * 1000
        print(f" | {cycle_time:5.1f}ms")
        
        # Wait 200ms between cycles
        time.sleep(0.2)


def main():
    """Main test function"""
    print("🧪 FlowControl Manual Instrument Test")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Configuration
    PORT = "/dev/ttyUSB0"
    ADDRESSES = [3, 5, 6]
    
    print(f"🔌 Target Port: {PORT}")
    print(f"📍 Target Addresses: {ADDRESSES}")
    
    # Test connections
    instruments = {}
    connected_addresses = []
    
    for address in ADDRESSES:
        instrument, success = test_instrument_connection(PORT, address)
        if success:
            instruments[address] = instrument
            connected_addresses.append(address)
    
    if not instruments:
        print("\n❌ No instruments connected. Check:")
        print("   - Is the USB device connected?")
        print("   - Are the instrument addresses correct?")
        print("   - Is /dev/ttyUSB0 the correct port?")
        print("   - Do you have permission to access the serial port?")
        return
    
    print(f"\n✅ Connected to {len(instruments)} instrument(s): {connected_addresses}")
    
    # Run measurement test
    try:
        test_continuous_measurements(instruments, ADDRESSES, duration=30)
    except KeyboardInterrupt:
        print("\n⚡ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🏁 Test completed!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()