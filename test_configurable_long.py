#!/usr/bin/env python3
"""
Configurable Long-Duration FlowControl Instrument Test
Easy to configure for different test durations and intervals
"""

import time
import sys
import os
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.thread_safe_propar import ThreadSafeProparInstrument

# ==================== CONFIGURATION ====================
# Modify these values to customize your test

TEST_DURATION_MINUTES = 30      # Test duration in minutes
CYCLE_INTERVAL_MS = 200         # Interval between measurements in milliseconds
PORT = "/dev/ttyUSB0"           # Serial port
ADDRESSES = [3, 5, 6]           # Instrument addresses to test
PRINT_EVERY_N_CYCLES = 25       # Print output every N cycles (25 = every 5 seconds at 200ms)

# Advanced settings
TIMEOUT_PER_INSTRUMENT = 3.0    # Timeout per instrument measurement (seconds)
ENABLE_DETAILED_ERRORS = True   # Show detailed error messages
SAVE_LOG_TO_FILE = True         # Save test log to file

# ========================================================

# DDE Parameter definitions
FSETPOINT_DDE = 206     # fSetpoint (float)
FMEASURE_DDE = 205      # fMeasure (float)
CAPACITY_DDE = 21       # capacity (float)
TYPE_DDE = 90           # type (string)
USERTAG_DDE = 115       # usertag (string)


class TestLogger:
    def __init__(self, save_to_file=False):
        self.save_to_file = save_to_file
        self.log_file = None
        if save_to_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.log_file = open(f"instrument_test_{timestamp}.log", "w")
    
    def log(self, message):
        print(message)
        if self.log_file:
            self.log_file.write(message + "\n")
            self.log_file.flush()
    
    def close(self):
        if self.log_file:
            self.log_file.close()


def test_instrument_connection(port, address, logger):
    """Test connection to a single instrument"""
    logger.log(f"\n🔧 Testing instrument at address {address}...")
    
    try:
        # Create instrument instance
        instrument = ThreadSafeProparInstrument(port, address=address)
        
        # Test basic parameters
        device_type = instrument.readParameter(TYPE_DDE)
        capacity = instrument.readParameter(CAPACITY_DDE)
        usertag = instrument.readParameter(USERTAG_DDE)
        
        logger.log(f"✅ Address {address}: Connection successful!")
        logger.log(f"   📋 Device Type: {device_type}")
        logger.log(f"   📊 Capacity: {capacity}")
        logger.log(f"   🏷️  User Tag: {usertag}")
        
        return instrument, True
        
    except Exception as e:
        logger.log(f"❌ Address {address}: Connection failed!")
        if ENABLE_DETAILED_ERRORS:
            logger.log(f"   ⚠️  Error: {e}")
        else:
            logger.log(f"   ⚠️  Error: {str(e)[:50]}...")
        return None, False


def test_continuous_measurements(instruments, addresses, duration_minutes, interval_ms, print_every_n, logger):
    """Test continuous measurements from connected instruments"""
    duration_seconds = duration_minutes * 60
    expected_cycles = int(duration_seconds * 1000 / interval_ms)
    
    logger.log(f"\n🚀 Starting {duration_minutes}-minute measurement test...")
    logger.log(f"⏱️  Duration: {duration_seconds}s, Interval: {interval_ms}ms")
    logger.log(f"📊 Expected cycles: ~{expected_cycles}")
    logger.log(f"📝 Printing every {print_every_n} cycles")
    logger.log("-" * 90)
    
    start_time = time.time()
    cycle = 0
    error_counts = {addr: 0 for addr in addresses}
    success_counts = {addr: 0 for addr in addresses}
    
    while (time.time() - start_time) < duration_seconds:
        cycle += 1
        cycle_start = time.perf_counter()
        
        # Calculate progress
        elapsed_total = time.time() - start_time
        remaining_time = duration_seconds - elapsed_total
        progress_percent = (elapsed_total / duration_seconds) * 100
        
        # Test all instruments
        cycle_results = {}
        for address in addresses:
            if address in instruments:
                try:
                    # Read measurement with timeout
                    start_read = time.perf_counter()
                    fmeasure = instruments[address].readParameter(FMEASURE_DDE)
                    fsetpoint = instruments[address].readParameter(FSETPOINT_DDE)
                    read_time = (time.perf_counter() - start_read) * 1000
                    
                    cycle_results[address] = {
                        'success': True,
                        'fmeasure': fmeasure,
                        'fsetpoint': fsetpoint,
                        'read_time': read_time
                    }
                    success_counts[address] += 1
                    
                except Exception as e:
                    cycle_results[address] = {
                        'success': False,
                        'error': str(e)[:20]
                    }
                    error_counts[address] += 1
            else:
                cycle_results[address] = {'success': False, 'error': 'DISCONNECTED'}
        
        # Print results every N cycles
        should_print = (cycle % print_every_n == 0) or (cycle == 1)
        
        if should_print:
            # Progress header
            logger.log(f"Cycle {cycle:5d} | {progress_percent:5.1f}% | {remaining_time:5.0f}s left")
            
            # Results for each instrument
            for address in sorted(addresses):
                result = cycle_results.get(address, {})
                if result.get('success'):
                    fmeasure = result.get('fmeasure', 'N/A')
                    fsetpoint = result.get('fsetpoint', 'N/A')
                    read_time = result.get('read_time', 0)
                    
                    if isinstance(fmeasure, (int, float)) and isinstance(fsetpoint, (int, float)):
                        logger.log(f"   Addr {address}: Flow={fmeasure:8.2f}, Setpoint={fsetpoint:8.2f} ({read_time:5.1f}ms)")
                    else:
                        logger.log(f"   Addr {address}: Flow={'N/A':>8}, Setpoint={'N/A':>8} ({read_time:5.1f}ms)")
                else:
                    error = result.get('error', 'Unknown')
                    logger.log(f"   Addr {address}: ERROR - {error}")
            
            # Show error statistics every 5 minutes
            if cycle % (5 * 60 * 1000 // interval_ms) == 0 and cycle > 1:
                logger.log("   📊 Error Summary:")
                for address in sorted(addresses):
                    total = success_counts[address] + error_counts[address]
                    if total > 0:
                        success_rate = (success_counts[address] / total) * 100
                        logger.log(f"      Addr {address}: {success_rate:5.1f}% success ({success_counts[address]}/{total})")
            
            logger.log("")  # Empty line for readability
        
        # Calculate cycle time and wait
        cycle_time = (time.perf_counter() - cycle_start) * 1000
        remaining_interval = (interval_ms - cycle_time) / 1000
        if remaining_interval > 0:
            time.sleep(remaining_interval)
    
    # Final statistics
    logger.log("\n" + "=" * 70)
    logger.log("📊 FINAL TEST STATISTICS")
    logger.log("=" * 70)
    
    for address in sorted(addresses):
        total = success_counts[address] + error_counts[address]
        if total > 0:
            success_rate = (success_counts[address] / total) * 100
            logger.log(f"Instrument {address}: {success_rate:5.1f}% success rate ({success_counts[address]}/{total} cycles)")
        else:
            logger.log(f"Instrument {address}: No data collected")


def main():
    """Main test function"""
    logger = TestLogger(save_to_file=SAVE_LOG_TO_FILE)
    
    logger.log("🧪 FlowControl Long-Duration Instrument Test")
    logger.log(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.log("=" * 70)
    logger.log(f"⚙️  Configuration:")
    logger.log(f"   Duration: {TEST_DURATION_MINUTES} minutes")
    logger.log(f"   Interval: {CYCLE_INTERVAL_MS}ms")
    logger.log(f"   Port: {PORT}")
    logger.log(f"   Addresses: {ADDRESSES}")
    logger.log(f"   Log file: {'Yes' if SAVE_LOG_TO_FILE else 'No'}")
    
    # Test connections
    instruments = {}
    connected_addresses = []
    
    for address in ADDRESSES:
        instrument, success = test_instrument_connection(PORT, address, logger)
        if success:
            instruments[address] = instrument
            connected_addresses.append(address)
    
    if not instruments:
        logger.log("\n❌ No instruments connected. Check:")
        logger.log("   - Is the USB device connected?")
        logger.log("   - Are the instrument addresses correct?")
        logger.log(f"   - Is {PORT} the correct port?")
        logger.log("   - Do you have permission to access the serial port?")
        logger.close()
        return
    
    logger.log(f"\n✅ Connected to {len(instruments)} instrument(s): {connected_addresses}")
    
    # Run measurement test
    try:
        test_continuous_measurements(
            instruments, 
            ADDRESSES, 
            TEST_DURATION_MINUTES, 
            CYCLE_INTERVAL_MS, 
            PRINT_EVERY_N_CYCLES, 
            logger
        )
    except KeyboardInterrupt:
        logger.log("\n⚡ Test interrupted by user")
    except Exception as e:
        logger.log(f"\n❌ Test failed: {e}")
        if ENABLE_DETAILED_ERRORS:
            import traceback
            logger.log(traceback.format_exc())
    
    logger.log("\n🏁 Test completed!")
    logger.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()