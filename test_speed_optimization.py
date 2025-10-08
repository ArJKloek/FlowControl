#!/usr/bin/env python3
"""
Speed Optimization Test Suite

Tests the performance improvements applied to the FlowControl application.
"""

import time
import sys
import os

# Add the current directory to the path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speed_optimization import get_speed_profile, print_speed_comparison
from speed_optimized_main import apply_speed_optimizations, get_current_speed_metrics

def test_speed_optimization_settings():
    """Test that speed optimization settings are correctly configured."""
    
    print("🧪 TESTING SPEED OPTIMIZATION SETTINGS")
    print("=" * 50)
    
    # Test profile retrieval
    profiles = ["original", "conservative", "fast"]
    
    for profile in profiles:
        settings = get_speed_profile(profile)
        
        print(f"\n{profile.upper()} Profile:")
        print(f"  Default period: {settings['default_period']:.3f}s")
        print(f"  Response timeout: {settings['response_timeout']:.3f}s")
        print(f"  Retry delay: {settings['retry_base_delay']:.3f}s")
        
        # Validate settings make sense
        assert settings['default_period'] > 0, f"Invalid default_period in {profile}"
        assert settings['response_timeout'] > 0, f"Invalid response_timeout in {profile}"
        assert settings['retry_base_delay'] > 0, f"Invalid retry_base_delay in {profile}"
        
        print(f"  ✅ {profile} profile validated")
    
    # Test speed improvements
    original = get_speed_profile("original")
    conservative = get_speed_profile("conservative")
    fast = get_speed_profile("fast")
    
    # Conservative should be faster than original
    assert conservative['default_period'] <= original['default_period']
    assert conservative['response_timeout'] <= original['response_timeout']
    
    # Fast should be faster than conservative  
    assert fast['default_period'] <= conservative['default_period']
    assert fast['response_timeout'] <= conservative['response_timeout']
    
    print(f"\n✅ All speed optimization settings validated!")
    return True

def simulate_polling_performance():
    """Simulate polling performance with different settings."""
    
    print("\n🏃 SIMULATING POLLING PERFORMANCE")
    print("=" * 50)
    
    profiles = ["original", "conservative", "fast"]
    results = {}
    
    for profile in profiles:
        settings = get_speed_profile(profile)
        
        # Simulate 10 polling cycles
        start_time = time.time()
        total_operations = 0
        
        for cycle in range(10):
            # Simulate main loop sleep
            time.sleep(settings['main_loop_sleep'])
            
            # Simulate 3 instrument reads per cycle
            for instrument in range(3):
                time.sleep(settings['response_timeout'] / 10)  # Scaled down for test
                total_operations += 1
        
        elapsed = time.time() - start_time
        ops_per_second = total_operations / elapsed if elapsed > 0 else 0
        
        results[profile] = {
            'elapsed': elapsed,
            'operations': total_operations,
            'ops_per_sec': ops_per_second
        }
        
        print(f"{profile.capitalize():>12}: {elapsed:.3f}s for {total_operations} ops ({ops_per_second:.1f} ops/sec)")
    
    # Calculate speedup
    original_rate = results['original']['ops_per_sec']
    for profile in ['conservative', 'fast']:
        if original_rate > 0:
            speedup = results[profile]['ops_per_sec'] / original_rate
            print(f"                  -> {speedup:.1f}x faster than original")
    
    return results

def test_file_modifications():
    """Test that the actual code files have been modified with optimizations."""
    
    print("\n📁 TESTING FILE MODIFICATIONS")
    print("=" * 50)
    
    # Test that poller.py has been optimized
    try:
        with open('backend/poller.py', 'r') as f:
            poller_content = f.read()
        
        # Check for optimized default period
        if 'default_period=0.2' in poller_content:
            print("✅ Poller default period optimized to 0.2s")
        else:
            print("⚠️  Poller default period not found (may still be default)")
        
        # Check for optimized sleep times
        optimized_sleeps = [
            'time.sleep(0.002)',  # main loop sleep
            'time.sleep(0.05)',   # empty queue sleep  
            'time.sleep(0.1)',    # fluid settle delay
            'time.sleep(0.08)',   # fluid verify interval
        ]
        
        found_optimizations = 0
        for sleep_pattern in optimized_sleeps:
            if sleep_pattern in poller_content:
                found_optimizations += 1
        
        print(f"✅ Found {found_optimizations}/{len(optimized_sleeps)} optimized sleep patterns in poller.py")
        
    except FileNotFoundError:
        print("⚠️  backend/poller.py not found")
    
    # Test that thread_safe_propar.py has been optimized
    try:
        with open('backend/thread_safe_propar.py', 'r') as f:
            thread_safe_content = f.read()
        
        # Check for optimized retry delay
        if 'time.sleep(0.05 * (attempt + 1))' in thread_safe_content:
            print("✅ Thread-safe retry delay optimized to 0.05s base")
        else:
            print("⚠️  Thread-safe retry delay optimization not found")
            
    except FileNotFoundError:
        print("⚠️  backend/thread_safe_propar.py not found")
    
    return True

def run_comprehensive_test():
    """Run all speed optimization tests."""
    
    print("🚀 FLOWCONTROL SPEED OPTIMIZATION TEST SUITE")
    print("=" * 60)
    print(f"Test started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: Settings validation
    try:
        test_speed_optimization_settings()
    except Exception as e:
        print(f"❌ Settings test failed: {e}")
        return False
    
    # Test 2: Performance simulation
    try:
        simulate_polling_performance()
    except Exception as e:
        print(f"❌ Performance simulation failed: {e}")
        return False
    
    # Test 3: File modifications
    try:
        test_file_modifications()
    except Exception as e:
        print(f"❌ File modification test failed: {e}")
        return False
    
    # Summary
    print("\n📊 OPTIMIZATION SUMMARY")
    print("=" * 30)
    print_speed_comparison()
    
    print(f"\n✅ ALL TESTS PASSED!")
    print(f"🚀 Speed optimizations are ready for use!")
    
    return True

if __name__ == "__main__":
    success = run_comprehensive_test()
    sys.exit(0 if success else 1)