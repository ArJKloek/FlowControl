#!/usr/bin/env python3
"""
Async Command Debug Test Script

This script demonstrates and tests the asynchronous command processing with detailed timing debug output.
"""

import time
import sys
import os

# Add the current directory to the path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def create_async_test_commands():
    """Create a test sequence to demonstrate async command processing."""
    
    test_code = '''
# ASYNC COMMAND TESTING - Add this to your application to test async performance

def test_async_commands(poller, test_address=3):
    """Test async commands with timing debug output."""
    
    print("\\n🚀 STARTING ASYNC COMMAND PERFORMANCE TEST")
    print("=" * 60)
    
    # Test 1: Async setpoint flow changes
    print("\\n📋 Test 1: Async Setpoint Flow Changes")
    test_values = [10.0, 25.0, 50.0, 75.0, 100.0]
    
    start_time = time.time()
    for i, value in enumerate(test_values):
        print(f"\\n--- Command {i+1}/5: Setting flow to {value} ---")
        poller.request_async_setpoint_flow(test_address, value, timeout=0.3)
        time.sleep(0.05)  # Small delay between commands to see sequencing
    
    # Wait for all commands to complete
    time.sleep(2.0)
    total_time = time.time() - start_time
    print(f"\\n✅ Test 1 Complete: 5 setpoint changes in {total_time:.2f}s")
    print(f"   Average per command: {total_time/5*1000:.1f}ms")
    
    # Test 2: Async setpoint percentage changes  
    print("\\n📋 Test 2: Async Setpoint Percentage Changes")
    test_percentages = [10, 30, 50, 80, 100]
    
    start_time = time.time()
    for i, percent in enumerate(test_percentages):
        print(f"\\n--- Command {i+1}/5: Setting {percent}% ---")
        poller.request_async_setpoint_pct(test_address, percent, timeout=0.3)
        time.sleep(0.05)
    
    time.sleep(2.0)
    total_time = time.time() - start_time
    print(f"\\n✅ Test 2 Complete: 5 percentage changes in {total_time:.2f}s")
    print(f"   Average per command: {total_time/5*1000:.1f}ms")
    
    # Test 3: Async fluid changes
    print("\\n📋 Test 3: Async Fluid Changes")
    test_fluids = [0, 1, 2, 3, 0]  # Cycle through fluid indexes
    
    start_time = time.time()
    for i, fluid_idx in enumerate(test_fluids):
        print(f"\\n--- Command {i+1}/5: Setting fluid {fluid_idx} ---")
        poller.request_async_fluid_change(test_address, fluid_idx, timeout=0.5)
        time.sleep(0.05)
    
    time.sleep(3.0)  # Fluid changes might take longer
    total_time = time.time() - start_time
    print(f"\\n✅ Test 3 Complete: 5 fluid changes in {total_time:.2f}s")
    print(f"   Average per command: {total_time/5*1000:.1f}ms")
    
    # Test 4: Async reads
    print("\\n📋 Test 4: Async Parameter Reads")
    
    start_time = time.time()
    for i in range(5):
        print(f"\\n--- Read {i+1}/5: Reading fMeasure ---")
        poller.request_async_read(test_address, 205, timeout=0.2)  # FMEASURE_DDE
        time.sleep(0.02)
    
    time.sleep(1.0)
    total_time = time.time() - start_time
    print(f"\\n✅ Test 4 Complete: 5 reads in {total_time:.2f}s")
    print(f"   Average per command: {total_time/5*1000:.1f}ms")
    
    # Test 5: Mixed command sequence
    print("\\n📋 Test 5: Mixed Async Commands")
    
    start_time = time.time()
    commands = [
        ("setpoint_flow", 45.0),
        ("read", 205),
        ("setpoint_pct", 60),
        ("read", 205),
        ("fluid", 1),
        ("read", 205),
        ("setpoint_flow", 80.0),
        ("read", 205)
    ]
    
    for i, (cmd_type, value) in enumerate(commands):
        print(f"\\n--- Mixed Command {i+1}/8: {cmd_type} {value} ---")
        if cmd_type == "setpoint_flow":
            poller.request_async_setpoint_flow(test_address, value, timeout=0.3)
        elif cmd_type == "setpoint_pct":
            poller.request_async_setpoint_pct(test_address, value, timeout=0.3)
        elif cmd_type == "fluid":
            poller.request_async_fluid_change(test_address, value, timeout=0.5)
        elif cmd_type == "read":
            poller.request_async_read(test_address, value, timeout=0.2)
        time.sleep(0.02)
    
    time.sleep(3.0)
    total_time = time.time() - start_time
    print(f"\\n✅ Test 5 Complete: 8 mixed commands in {total_time:.2f}s")
    print(f"   Average per command: {total_time/8*1000:.1f}ms")
    
    print("\\n🏆 ASYNC PERFORMANCE TEST COMPLETE!")
    print("Check the debug output above for detailed timing information.")

# Example usage:
# test_async_commands(your_poller, test_address=3)
'''
    
    return test_code

def create_debug_analysis_tool():
    """Create a tool to analyze the debug output."""
    
    analysis_code = '''
# ASYNC DEBUG OUTPUT ANALYSIS TOOL

import re

def analyze_async_debug_output(log_text):
    """Analyze async debug output to extract performance metrics."""
    
    # Patterns for different debug messages
    reply_pattern = r"Reply received for (\\w+) \\(addr (\\d+)\\) in ([\\d.]+)ms"
    timeout_pattern = r"Timeout \\(([\\d.]+)ms\\) for (\\w+) \\(addr (\\d+)\\)"
    execution_pattern = r"(\\w+) write completed in ([\\d.]+)ms, result=(\\w+)"
    stats_pattern = r"ASYNC STATS: Avg=([\\d.]+)ms, Range=([\\d.]+)-([\\d.]+)ms, Count=(\\d+)"
    
    # Extract timing data
    reply_times = []
    timeouts = []
    execution_times = []
    
    # Find all reply times
    for match in re.finditer(reply_pattern, log_text):
        command, address, time_ms = match.groups()
        reply_times.append({
            'command': command,
            'address': int(address),
            'time_ms': float(time_ms)
        })
    
    # Find all timeouts
    for match in re.finditer(timeout_pattern, log_text):
        timeout_ms, command, address = match.groups()
        timeouts.append({
            'command': command,
            'address': int(address),
            'timeout_ms': float(timeout_ms)
        })
    
    # Find all execution times
    for match in re.finditer(execution_pattern, log_text):
        command, time_ms, result = match.groups()
        execution_times.append({
            'command': command,
            'time_ms': float(time_ms),
            'result': result
        })
    
    # Generate analysis report
    print("\\n📊 ASYNC DEBUG ANALYSIS REPORT")
    print("=" * 50)
    
    if reply_times:
        times = [rt['time_ms'] for rt in reply_times]
        print(f"\\n✅ SUCCESSFUL REPLIES ({len(reply_times)} commands):")
        print(f"   Average response time: {sum(times)/len(times):.2f}ms")
        print(f"   Fastest response: {min(times):.2f}ms")
        print(f"   Slowest response: {max(times):.2f}ms")
        print(f"   Response time range: {max(times)-min(times):.2f}ms")
        
        # Group by command type
        by_command = {}
        for rt in reply_times:
            cmd = rt['command']
            if cmd not in by_command:
                by_command[cmd] = []
            by_command[cmd].append(rt['time_ms'])
        
        print("\\n   By command type:")
        for cmd, times in by_command.items():
            avg_time = sum(times) / len(times)
            print(f"     {cmd}: {avg_time:.2f}ms avg ({len(times)} samples)")
    
    if timeouts:
        print(f"\\n⏰ TIMEOUTS ({len(timeouts)} commands):")
        for timeout in timeouts:
            print(f"   {timeout['command']} (addr {timeout['address']}): {timeout['timeout_ms']:.0f}ms")
    
    if execution_times:
        times = [et['time_ms'] for et in execution_times]
        print(f"\\n⚡ EXECUTION TIMES ({len(execution_times)} operations):")
        print(f"   Average execution: {sum(times)/len(times):.2f}ms")
        print(f"   Fastest execution: {min(times):.2f}ms")
        print(f"   Slowest execution: {max(times):.2f}ms")
    
    # Performance summary
    total_commands = len(reply_times) + len(timeouts)
    if total_commands > 0:
        success_rate = len(reply_times) / total_commands * 100
        print(f"\\n🎯 PERFORMANCE SUMMARY:")
        print(f"   Total commands: {total_commands}")
        print(f"   Success rate: {success_rate:.1f}%")
        print(f"   Timeout rate: {100-success_rate:.1f}%")
        
        if reply_times:
            avg_response = sum(rt['time_ms'] for rt in reply_times) / len(reply_times)
            if avg_response < 50:
                print(f"   🚀 EXCELLENT: Average {avg_response:.1f}ms response")
            elif avg_response < 100:
                print(f"   ✅ GOOD: Average {avg_response:.1f}ms response")
            elif avg_response < 200:
                print(f"   ⚠️  FAIR: Average {avg_response:.1f}ms response")
            else:
                print(f"   ❌ SLOW: Average {avg_response:.1f}ms response")

# Usage example:
# log_output = "... paste your debug output here ..."
# analyze_async_debug_output(log_output)
'''
    
    return analysis_code

def main():
    print("🚀 ASYNC COMMAND DEBUG TOOLS")
    print("=" * 40)
    
    print("\\n1. Test Commands:")
    test_code = create_async_test_commands()
    print("   Copy the following code to test async commands:")
    print("   (Save as 'test_async_commands.py')")
    
    with open('test_async_commands.py', 'w', encoding='utf-8') as f:
        f.write(test_code)
    print("   ✅ Saved as 'test_async_commands.py'")
    
    print("\\n2. Debug Analysis Tool:")
    analysis_code = create_debug_analysis_tool()
    print("   Copy the following code to analyze debug output:")
    print("   (Save as 'analyze_async_debug.py')")
    
    with open('analyze_async_debug.py', 'w', encoding='utf-8') as f:
        f.write(analysis_code)
    print("   ✅ Saved as 'analyze_async_debug.py'")
    
    print("\\n📋 USAGE INSTRUCTIONS:")
    print("=" * 30)
    print("1. Run your FlowControl application")
    print("2. Use the async commands (request_async_setpoint_flow, etc.)")
    print("3. Watch the console for debug output like:")
    print("   🚀 ASYNC DEBUG: 📤 Started async_fset_flow...")
    print("   🚀 ASYNC DEBUG: ✅ Reply received for async_fset_flow in 15.43ms")
    print("   📊 ASYNC STATS: Avg=18.2ms, Range=12.1-25.4ms, Count=5")
    print("4. Copy the debug output and use analyze_async_debug.py to get performance stats")
    
    print("\\n🎯 WHAT TO LOOK FOR:")
    print("- Reply times under 50ms = Excellent performance")
    print("- Reply times 50-100ms = Good performance") 
    print("- Reply times over 200ms = May need optimization")
    print("- Timeouts at 400ms = Instrument not responding")

if __name__ == "__main__":
    main()