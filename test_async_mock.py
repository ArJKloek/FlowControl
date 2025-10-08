#!/usr/bin/env python3
"""
Simple Async Test for FlowControl - Works without hardware for testing
"""

import asyncio
import time
import random
from datetime import datetime


class MockInstrument:
    """Mock instrument for testing async behavior"""
    def __init__(self, address):
        self.address = address
        self.base_flow = random.uniform(10, 100)
        
    def readParameter(self, dde_nr):
        """Simulate parameter reading with some delay"""
        time.sleep(random.uniform(0.05, 0.2))  # Simulate instrument response time
        
        if dde_nr == 205:  # fMeasure
            # Add some random variation to simulate real flow
            return self.base_flow + random.uniform(-5, 5)
        elif dde_nr == 206:  # fSetpoint
            return self.base_flow
        elif dde_nr == 21:   # Capacity
            return 100.0
        elif dde_nr == 90:   # Type
            return f"EL-FLOW-{self.address}"
        else:
            return f"PARAM_{dde_nr}"


class AsyncInstrumentTester:
    def __init__(self, addresses=[3, 5, 6]):
        self.addresses = addresses
        self.instruments = {}
        self.test_results = {}
        
    async def connect_instruments(self):
        """Connect to mock instruments"""
        print(f"🔌 Connecting to mock instruments")
        print(f"📍 Target addresses: {self.addresses}")
        print("-" * 50)
        
        for address in self.addresses:
            try:
                print(f"Connecting to address {address}...")
                instrument = MockInstrument(address)
                
                # Test basic connection
                device_type = instrument.readParameter(90)  # TYPE_DDE
                print(f"✅ Address {address}: Connected - Type: {device_type}")
                
                self.instruments[address] = instrument
                self.test_results[address] = {
                    'connected': True,
                    'device_type': device_type,
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

    def test_single_measurement(self, address):
        """Test measurement from a single instrument (synchronous)"""
        if address not in self.instruments:
            return None
            
        instrument = self.instruments[address]
        start_time = time.perf_counter()
        
        try:
            # Read key parameters
            fmeasure = instrument.readParameter(205)   # Flow measurement
            capacity = instrument.readParameter(21)    # Capacity
            fsetpoint = instrument.readParameter(206)  # Setpoint
            
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
        """Async wrapper for measurement"""
        # Small delay to simulate async behavior
        await asyncio.sleep(0.001)
        return await asyncio.get_event_loop().run_in_executor(None, self.test_single_measurement, address)

    async def continuous_measurement_test(self, duration_seconds=60, interval_ms=200):
        """Run continuous measurements for specified duration"""
        print(f"🚀 Starting continuous measurement test")
        print(f"⏱️  Duration: {duration_seconds}s ({duration_seconds/60:.1f} minutes), Interval: {interval_ms}ms")
        print(f"🎯 Testing {len(self.instruments)} mock instruments")
        print(f"📊 Expected cycles: ~{int(duration_seconds * 1000 / interval_ms)}")
        print("-" * 80)
        
        start_time = time.time()
        cycle_count = 0
        
        while (time.time() - start_time) < duration_seconds:
            cycle_start = time.perf_counter()
            cycle_count += 1
            
            # Test all instruments concurrently
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
            
            # Print cycle results with progress indication
            cycle_time = (time.perf_counter() - cycle_start) * 1000
            elapsed_total = time.time() - start_time
            remaining_time = duration_seconds - elapsed_total
            progress_percent = (elapsed_total / duration_seconds) * 100
            
            # Print every 10th cycle or every 30 seconds, whichever is more frequent
            should_print = (cycle_count % 10 == 0) or (cycle_count % max(1, int(30000/interval_ms)) == 0)
            
            if should_print:
                print(f"Cycle {cycle_count:4d} ({progress_percent:5.1f}% - {remaining_time:5.0f}s left) ({cycle_time:6.1f}ms):", end=" ")
                
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
                
            print(f"   ✅ Connection: SUCCESS - Type: {result.get('device_type', 'Unknown')}")
            
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
                            if isinstance(fmeasure, (int, float)):
                                print(f"      {m['timestamp']}: Flow={fmeasure:.2f}, Capacity={capacity:.2f}, Setpoint={fsetpoint:.2f}")
                            else:
                                print(f"      {m['timestamp']}: Flow={fmeasure}, Capacity={capacity}, Setpoint={fsetpoint}")
                
                if errors:
                    print(f"   ⚠️  Recent Errors:")
                    for error in errors[-3:]:  # Show last 3 errors
                        print(f"      - {error['timestamp']}: {error['error']}")


async def main():
    """Main test function"""
    print("🧪 FlowControl Async Test (Mock Instruments)")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Initialize tester with mock instruments
    tester = AsyncInstrumentTester(addresses=[3, 5, 6])
    
    # Connect to instruments
    connected_count = await tester.connect_instruments()
    
    if connected_count == 0:
        print("❌ No instruments connected. Exiting.")
        return
    
    print(f"✅ Connected to {connected_count} mock instrument(s)")
    
    # Run continuous test
    try:
        await tester.continuous_measurement_test(duration_seconds=60, interval_ms=200)  # 1 minute for testing
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