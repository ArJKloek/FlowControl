#!/usr/bin/env python3
"""
Test script to verify extreme spike generation and logging
"""
import time
import sys
import os

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.dummy_instrument import DummyInstrument

def test_spike_logging():
    print("Testing extreme spike generation and logging...")
    
    # Create a dummy instrument
    dummy = DummyInstrument(port="DUMMY0", address=1)
    
    # Enable extreme testing with 3-second intervals for faster testing
    dummy.enable_extreme_test(enabled=True, interval_seconds=3.0)
    print("Enabled extreme testing with 3-second intervals")
    
    print("\nMonitoring for spikes (will run for 15 seconds)...")
    start_time = time.time()
    last_measurement = None
    spike_count = 0
    
    while (time.time() - start_time) < 15:
        # Simulate getting a measurement (like the poller would)
        measurement = dummy._simulate_fmeasure()
        
        # Check if this is a spike
        if measurement >= 1000000.0:
            spike_count += 1
            print(f"★ SPIKE DETECTED: {measurement} at {time.time() - start_time:.1f}s")
        else:
            # Only print normal values occasionally to reduce clutter
            if time.time() % 2 < 0.1:  # Print every ~2 seconds
                print(f"  Normal value: {measurement:.2f}")
        
        last_measurement = measurement
        time.sleep(0.1)  # Simulate polling frequency
    
    print(f"\nTest completed!")
    print(f"Total spikes detected: {spike_count}")
    print(f"Expected spikes: ~{15 // 3} (one every 3 seconds)")

if __name__ == "__main__":
    test_spike_logging()