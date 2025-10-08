#!/usr/bin/env python3
"""
Speed Optimization Configuration for FlowControl Application

This module provides optimized settings for faster operation while maintaining
stability and crash prevention benefits.
"""

# ===== POLLING SPEED OPTIMIZATIONS =====

# Default polling period - reduced from 0.5s to 0.2s for faster updates
FAST_DEFAULT_PERIOD = 0.2  # seconds (was 0.5s = 2.5x faster)

# Minimum polling interval - reduced for more responsive updates  
FAST_MIN_POLLING_INTERVAL = 0.05  # seconds (was 0.1s = 2x faster)

# Sleep delays in main polling loop - reduced for responsiveness
FAST_MAIN_LOOP_SLEEP = 0.002  # seconds (was 0.005s = 2.5x faster)
FAST_EMPTY_QUEUE_SLEEP = 0.05  # seconds (was 0.1s = 2x faster)

# ===== THREAD-SAFE COMMUNICATION OPTIMIZATIONS =====

# Retry delays - reduced for faster recovery
FAST_RETRY_BASE_DELAY = 0.05  # seconds (was 0.1s = 2x faster)
FAST_RETRY_MAX_DELAY = 0.2   # seconds (was progressive up to 0.3s)

# Port lock acquisition timeout
FAST_PORT_LOCK_TIMEOUT = 0.1  # seconds (faster timeout for busy detection)

# ===== PROPAR COMMUNICATION OPTIMIZATIONS =====

# Response timeouts - optimized for speed while maintaining reliability
FAST_RESPONSE_TIMEOUT = 0.04    # seconds (was 0.06s = 1.5x faster)
FAST_SERIAL_TIMEOUT = 0.002     # seconds (was 0.003s = 1.5x faster)

# Write operation timeouts - slightly faster
FAST_WRITE_TIMEOUT = 0.08       # seconds (was 0.20s = 2.5x faster)

# ===== VERIFICATION AND SETTLING OPTIMIZATIONS =====

# Fluid switching verification delays - reduced
FAST_FLUID_SETTLE_DELAY = 0.1   # seconds (was 0.2s = 2x faster)
FAST_FLUID_VERIFY_INTERVAL = 0.08  # seconds (was 0.15s = ~2x faster)

# Setpoint verification timing
FAST_SETPOINT_SETTLE = 0.03     # seconds (was 0.05s)

# ===== BULK OPERATION OPTIMIZATIONS =====

# Use bulk reads more aggressively - group multiple parameters
ENABLE_BULK_READS = True
MAX_BULK_PARAMS = 8  # Read up to 8 parameters in one operation

# Cache parameter lookups to avoid repeated database queries
ENABLE_PARAM_CACHE = True

# ===== CONSERVATIVE SPEED SETTINGS (FALLBACK) =====

# If fast settings cause issues, use these conservative but still improved settings
CONSERVATIVE_DEFAULT_PERIOD = 0.3  # seconds (was 0.5s = 1.7x faster)
CONSERVATIVE_RESPONSE_TIMEOUT = 0.05  # seconds (was 0.06s = 1.2x faster)
CONSERVATIVE_RETRY_DELAY = 0.08  # seconds (was 0.1s = 1.25x faster)

def get_speed_profile(profile="fast"):
    """
    Get optimized settings for different speed profiles.
    
    Args:
        profile (str): "fast", "conservative", or "original"
    
    Returns:
        dict: Configuration settings for the requested profile
    """
    
    if profile == "fast":
        return {
            "default_period": FAST_DEFAULT_PERIOD,
            "min_polling_interval": FAST_MIN_POLLING_INTERVAL,
            "main_loop_sleep": FAST_MAIN_LOOP_SLEEP,
            "empty_queue_sleep": FAST_EMPTY_QUEUE_SLEEP,
            "retry_base_delay": FAST_RETRY_BASE_DELAY,
            "retry_max_delay": FAST_RETRY_MAX_DELAY,
            "response_timeout": FAST_RESPONSE_TIMEOUT,
            "serial_timeout": FAST_SERIAL_TIMEOUT,
            "write_timeout": FAST_WRITE_TIMEOUT,
            "fluid_settle_delay": FAST_FLUID_SETTLE_DELAY,
            "fluid_verify_interval": FAST_FLUID_VERIFY_INTERVAL,
            "setpoint_settle": FAST_SETPOINT_SETTLE,
            "enable_bulk_reads": ENABLE_BULK_READS,
            "max_bulk_params": MAX_BULK_PARAMS,
            "enable_param_cache": ENABLE_PARAM_CACHE,
        }
    
    elif profile == "conservative":
        return {
            "default_period": CONSERVATIVE_DEFAULT_PERIOD,
            "min_polling_interval": FAST_MIN_POLLING_INTERVAL,
            "main_loop_sleep": FAST_MAIN_LOOP_SLEEP,
            "empty_queue_sleep": FAST_EMPTY_QUEUE_SLEEP,
            "retry_base_delay": CONSERVATIVE_RETRY_DELAY,
            "retry_max_delay": FAST_RETRY_MAX_DELAY,
            "response_timeout": CONSERVATIVE_RESPONSE_TIMEOUT,
            "serial_timeout": FAST_SERIAL_TIMEOUT,
            "write_timeout": FAST_WRITE_TIMEOUT,
            "fluid_settle_delay": FAST_FLUID_SETTLE_DELAY,
            "fluid_verify_interval": FAST_FLUID_VERIFY_INTERVAL,
            "setpoint_settle": FAST_SETPOINT_SETTLE,
            "enable_bulk_reads": ENABLE_BULK_READS,
            "max_bulk_params": MAX_BULK_PARAMS,
            "enable_param_cache": ENABLE_PARAM_CACHE,
        }
    
    else:  # original
        return {
            "default_period": 0.5,
            "min_polling_interval": 0.1,
            "main_loop_sleep": 0.005,
            "empty_queue_sleep": 0.1,
            "retry_base_delay": 0.1,
            "retry_max_delay": 0.3,
            "response_timeout": 0.06,
            "serial_timeout": 0.003,
            "write_timeout": 0.20,
            "fluid_settle_delay": 0.2,
            "fluid_verify_interval": 0.15,
            "setpoint_settle": 0.05,
            "enable_bulk_reads": False,
            "max_bulk_params": 4,
            "enable_param_cache": False,
        }

def print_speed_comparison():
    """Print a comparison of different speed profiles."""
    
    profiles = ["original", "conservative", "fast"]
    settings = {profile: get_speed_profile(profile) for profile in profiles}
    
    print("🚀 SPEED OPTIMIZATION COMPARISON")
    print("=" * 60)
    
    key_metrics = [
        ("default_period", "Default Polling Period", "s"),
        ("response_timeout", "Response Timeout", "s"), 
        ("retry_base_delay", "Retry Delay", "s"),
        ("main_loop_sleep", "Main Loop Sleep", "s"),
    ]
    
    for key, name, unit in key_metrics:
        print(f"\n{name} ({unit}):")
        original = settings["original"][key]
        for profile in profiles:
            value = settings[profile][key]
            if profile == "original":
                speedup = 1.0
                indicator = ""
            else:
                speedup = original / value if value > 0 else float('inf')
                indicator = f" ({speedup:.1f}x faster)" if speedup > 1 else ""
            
            print(f"  {profile.capitalize():>12}: {value:>6} {unit}{indicator}")
    
    print(f"\n📊 ESTIMATED OVERALL SPEEDUP:")
    print(f"  Conservative: ~1.5-2x faster than original")
    print(f"  Fast:         ~2-3x faster than original")
    print(f"\n⚠️  Note: Actual speedup depends on hardware and network conditions")

if __name__ == "__main__":
    print_speed_comparison()