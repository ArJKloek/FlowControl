#!/usr/bin/env python3
"""
Cross-platform Serial Port Detection and Instrument Test
Tests communication with FlowControl instruments on available serial ports
"""

import asyncio
import time
import sys
import os
from datetime import datetime
import serial.tools.list_ports

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.thread_safe_propar import ThreadSafeProparInstrument

# DDE Parameter definitions (from poller.py)
FSETPOINT_DDE = 206     # fSetpoint (float)
FMEASURE_DDE = 205      # fMeasure (float)
SETPOINT_DDE = 9        # setpoint (int, 32000 = 100%)
MEASURE_DDE = 8         # measure (int, 32000 = 100%)
CAPACITY_DDE = 21       # capacity (float)
TYPE_DDE = 90           # type (string)
USERTAG_DDE = 115       # usertag (string)


class PortDetector:
    @staticmethod
    def list_available_ports():
        """List all available serial ports"""
        ports = serial.tools.list_ports.comports()
        available_ports = []
        
        print("🔍 Scanning for available serial ports:")
        for port in ports:
            port_info = {
                'device': port.device,
                'description': port.description,
                'manufacturer': getattr(port, 'manufacturer', 'Unknown')
            }
            available_ports.append(port_info)
            print(f"   📍 {port.device}: {port.description}")
        
        return available_ports
    
    @staticmethod
    def suggest_target_port():
        """Suggest the most likely port for FlowControl instruments"""
        ports = serial.tools.list_ports.comports()
        
        # Look for USB-to-serial adapters
        for port in ports:
            desc_lower = port.description.lower()
            manufacturer = getattr(port, 'manufacturer', '').lower()
            
            # Common USB-to-serial adapter patterns
            if any(keyword in desc_lower for keyword in ['usb', 'serial', 'ch340', 'ftdi', 'cp210']):
                return port.device
                
            if any(keyword in manufacturer for keyword in ['ftdi', 'prolific', 'ch340']):
                return port.device
        
        # On Linux, look for /dev/ttyUSB* or /dev/ttyACM*
        if sys.platform.startswith('linux'):
            for port in ports:
                if '/dev/ttyUSB' in port.device or '/dev/ttyACM' in port.device:
                    return port.device
        
        # Return first available port as fallback
        if ports:
            return ports[0].device
            
        return None


class InstrumentTester:
    def __init__(self, port=None, addresses=[3, 5, 6]):
        if port is None:
            self.port = PortDetector.suggest_target_port()
        else:
            self.port = port
            
        self.addresses = addresses
        self.instruments = {}
        self.test_results = {}
        
    async def connect_instruments(self):
        """Connect to all instruments"""
        if self.port is None:
            print("❌ No serial ports available!")
            return 0
            
        print(f"🔌 Connecting to instruments on {self.port}")
        print(f"📍 Target addresses: {self.addresses}")
        print("-" * 50)
        
        for address in self.addresses:
            try:
                print(f"Connecting to address {address}...")
                instrument = ThreadSafeProparInstrument(self.port, address=address)
                
                # Test basic connection by reading device type
                device_type = instrument.readParameter(TYPE_DDE)
                capacity = instrument.readParameter(CAPACITY_DDE)
                
                print(f"✅ Address {address}: Connected")
                print(f"   📋 Type: {device_type}")
                print(f"   📊 Capacity: {capacity}")
                
                self.instruments[address] = instrument
                self.test_results[address] = {
                    'connected': True,
                    'device_type': device_type,
                    'capacity': capacity,
                    'measurements': [],
                    'errors': []
                }
                
            except Exception as e:
                print(f"❌ Address {address}: Connection failed - {e}")
                self.test_results[address] = {
                    'connected': False,
                    'error': str(e),
                    'measurements': [],
                    'errors': []
                }
        
        print("-" * 50)
        return len(self.instruments)

    async def test_single_measurement(self, address):
        """Test measurement from a single instrument"""
        if address not in self.instruments:
            return None
            
        instrument = self.instruments[address]
        start_time = time.perf_counter()
        
        try:
            # Read key parameters
            fmeasure = instrument.readParameter(FMEASURE_DDE)    # Flow measurement (float)
            capacity = instrument.readParameter(CAPACITY_DDE)   # Capacity (float)
            fsetpoint = instrument.readParameter(FSETPOINT_DDE) # Setpoint (float)
            
            end_time = time.perf_counter()
            response_time = (end_time - start_time) * 1000  # ms
            
            result = {
                'timestamp': datetime.now().strftime('%H:%M:%S.%f')[:-3],
                'response_time_ms': round(response_time, 1),
                'fmeasure': fmeasure,
                'capacity': capacity, 
                'fsetpoint': fsetpoint,
                'success': True
            }
            
            self.test_results[address]['measurements'].append(result)
            return result
            
        except Exception as e:
            end_time = time.perf_counter()
            response_time = (end_time - start_time) * 1000
            
            error_result = {
                'timestamp': datetime.now().strftime('%H:%M:%S.%f')[:-3],
                'response_time_ms': round(response_time, 1),
                'error': str(e),
                'success': False
            }
            
            self.test_results[address]['errors'].append(error_result)
            return error_result

    async def _async_measurement(self, address):
        """Async wrapper for measurement (simulates concurrent execution)"""
        # Small delay to simulate async behavior
        await asyncio.sleep(0.001)
        return await asyncio.get_event_loop().run_in_executor(None, self.test_single_measurement, address)

    async def continuous_measurement_test(self, duration_seconds=30, interval_ms=200):
        """Run continuous measurements for specified duration"""
        print(f"🚀 Starting continuous measurement test")
        print(f"⏱️  Duration: {duration_seconds}s, Interval: {interval_ms}ms")
        print(f"🎯 Testing {len(self.instruments)} instruments")
        print("-" * 90)
        
        start_time = time.time()
        cycle_count = 0
        
        while (time.time() - start_time) < duration_seconds:
            cycle_start = time.perf_counter()
            cycle_count += 1
            
            # Test all instruments concurrently (simulated with asyncio.sleep)
            tasks = []
            for address in self.instruments.keys():
                task = asyncio.create_task(self._async_measurement(address))
                tasks.append((address, task))
            
            # Wait for all measurements
            results = {}
            for address, task in tasks:
                try:
                    result = await asyncio.wait_for(task, timeout=3.0)
                    results[address] = result
                except asyncio.TimeoutError:
                    results[address] = {
                        'timestamp': datetime.now().strftime('%H:%M:%S.%f')[:-3],
                        'error': 'Timeout (3s)',
                        'success': False
                    }
            
            # Print cycle results
            cycle_time = (time.perf_counter() - cycle_start) * 1000
            print(f"Cycle {cycle_count:3d} ({cycle_time:6.1f}ms):", end=" ")
            
            for address in sorted(self.instruments.keys()):
                result = results.get(address, {})
                if result.get('success'):
                    fmeasure = result.get('fmeasure', 'N/A')
                    response_time = result.get('response_time_ms', 0)
                    if isinstance(fmeasure, (int, float)):
                        print(f"Addr{address}:{fmeasure:>8.2f}({response_time:4.0f}ms)", end=" ")
                    else:
                        print(f"Addr{address}:{'N/A':>8}({response_time:4.0f}ms)", end=" ")
                else:
                    error = str(result.get('error', 'Unknown'))[:8]
                    print(f"Addr{address}:{'ERROR':>8}({error})", end=" ")
            
            print()  # New line
            
            # Wait for next interval
            elapsed = (time.perf_counter() - cycle_start) * 1000
            if elapsed < interval_ms:
                await asyncio.sleep((interval_ms - elapsed) / 1000)

    def print_summary(self):
        """Print test summary statistics"""
        print("\n" + "=" * 70)
        print("📊 TEST SUMMARY")
        print("=" * 70)
        
        for address in sorted(self.test_results.keys()):
            result = self.test_results[address]
            print(f"\n🔧 Instrument Address {address}:")
            
            if not result['connected']:
                print(f"   ❌ Connection: FAILED - {result.get('error', 'Unknown')}")
                continue
                
            print(f"   ✅ Connection: SUCCESS")
            print(f"   📋 Type: {result.get('device_type', 'Unknown')}")
            print(f"   📊 Capacity: {result.get('capacity', 'Unknown')}")
            
            measurements = result['measurements']
            errors = result['errors']
            total_attempts = len(measurements) + len(errors)
            
            if total_attempts > 0:
                success_rate = (len(measurements) / total_attempts) * 100
                print(f"   📈 Success Rate: {success_rate:.1f}% ({len(measurements)}/{total_attempts})")
                
                if measurements:
                    response_times = [m['response_time_ms'] for m in measurements]
                    avg_response = sum(response_times) / len(response_times)
                    min_response = min(response_times)
                    max_response = max(response_times)
                    print(f"   ⏱️  Response Time: avg={avg_response:.1f}ms, min={min_response:.1f}ms, max={max_response:.1f}ms")
                    
                    # Show recent measurement values
                    recent_measurements = measurements[-3:]  # Last 3 measurements
                    if recent_measurements:
                        print(f"   📊 Recent Values:")
                        for m in recent_measurements:
                            fmeasure = m.get('fmeasure', 'N/A')
                            capacity = m.get('capacity', 'N/A')
                            fsetpoint = m.get('fsetpoint', 'N/A')
                            print(f"      {m['timestamp']}: Flow={fmeasure}, Capacity={capacity}, Setpoint={fsetpoint}")
                
                if errors:
                    print(f"   ⚠️  Recent Errors:")
                    for error in errors[-3:]:  # Show last 3 errors
                        print(f"      - {error['timestamp']}: {error['error']}")


async def main():
    """Main test function"""
    print("🧪 FlowControl Cross-Platform Instrument Test")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Detect available ports
    available_ports = PortDetector.list_available_ports()
    if not available_ports:
        print("❌ No serial ports found!")
        return
    
    suggested_port = PortDetector.suggest_target_port()
    print(f"\n💡 Suggested port: {suggested_port}")
    
    # Allow manual port selection
    print(f"\nPress Enter to use {suggested_port}, or type a different port:")
    user_input = input("Port: ").strip()
    if user_input:
        target_port = user_input
    else:
        target_port = suggested_port
    
    print(f"\n🎯 Using port: {target_port}")
    
    # Initialize tester
    tester = InstrumentTester(port=target_port, addresses=[3, 5, 6])
    
    # Connect to instruments
    connected_count = await tester.connect_instruments()
    
    if connected_count == 0:
        print("❌ No instruments connected. Exiting.")
        return
    
    print(f"✅ Connected to {connected_count} instrument(s)")
    
    # Run continuous test
    try:
        await tester.continuous_measurement_test(duration_seconds=30, interval_ms=200)
    except KeyboardInterrupt:
        print("\n⚡ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Print summary
    tester.print_summary()
    
    print("\n🏁 Test completed!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()