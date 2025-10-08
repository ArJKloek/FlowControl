
# ASYNC DEBUG OUTPUT ANALYSIS TOOL

import re

def analyze_async_debug_output(log_text):
    """Analyze async debug output to extract performance metrics."""
    
    # Patterns for different debug messages
    reply_pattern = r"Reply received for (\w+) \(addr (\d+)\) in ([\d.]+)ms"
    timeout_pattern = r"Timeout \(([\d.]+)ms\) for (\w+) \(addr (\d+)\)"
    execution_pattern = r"(\w+) write completed in ([\d.]+)ms, result=(\w+)"
    stats_pattern = r"ASYNC STATS: Avg=([\d.]+)ms, Range=([\d.]+)-([\d.]+)ms, Count=(\d+)"
    
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
    print("\n📊 ASYNC DEBUG ANALYSIS REPORT")
    print("=" * 50)
    
    if reply_times:
        times = [rt['time_ms'] for rt in reply_times]
        print(f"\n✅ SUCCESSFUL REPLIES ({len(reply_times)} commands):")
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
        
        print("\n   By command type:")
        for cmd, times in by_command.items():
            avg_time = sum(times) / len(times)
            print(f"     {cmd}: {avg_time:.2f}ms avg ({len(times)} samples)")
    
    if timeouts:
        print(f"\n⏰ TIMEOUTS ({len(timeouts)} commands):")
        for timeout in timeouts:
            print(f"   {timeout['command']} (addr {timeout['address']}): {timeout['timeout_ms']:.0f}ms")
    
    if execution_times:
        times = [et['time_ms'] for et in execution_times]
        print(f"\n⚡ EXECUTION TIMES ({len(execution_times)} operations):")
        print(f"   Average execution: {sum(times)/len(times):.2f}ms")
        print(f"   Fastest execution: {min(times):.2f}ms")
        print(f"   Slowest execution: {max(times):.2f}ms")
    
    # Performance summary
    total_commands = len(reply_times) + len(timeouts)
    if total_commands > 0:
        success_rate = len(reply_times) / total_commands * 100
        print(f"\n🎯 PERFORMANCE SUMMARY:")
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
