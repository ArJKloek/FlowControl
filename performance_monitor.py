#!/usr/bin/env python3
"""
Performance Monitor for FlowControl Application
Tracks UI responsiveness and polling performance improvements
"""

import time
import threading
import sys
import os

class PerformanceMonitor:
    """Monitor application performance metrics"""
    
    def __init__(self):
        self.start_time = time.time()
        self.poll_times = []
        self.ui_updates = 0
        self.async_commands = 0
        self.last_update = time.time()
        
    def log_poll_time(self, duration_ms):
        """Log a polling cycle time"""
        self.poll_times.append(duration_ms)
        if len(self.poll_times) > 100:  # Keep last 100 measurements
            self.poll_times.pop(0)
            
    def log_ui_update(self):
        """Log a UI update event"""
        self.ui_updates += 1
        self.last_update = time.time()
        
    def log_async_command(self):
        """Log an async command execution"""
        self.async_commands += 1
        
    def get_stats(self):
        """Get current performance statistics"""
        now = time.time()
        runtime = now - self.start_time
        
        stats = {
            'runtime_seconds': runtime,
            'poll_count': len(self.poll_times),
            'ui_updates': self.ui_updates,
            'async_commands': self.async_commands,
        }
        
        if self.poll_times:
            stats.update({
                'avg_poll_time_ms': sum(self.poll_times) / len(self.poll_times),
                'min_poll_time_ms': min(self.poll_times),
                'max_poll_time_ms': max(self.poll_times),
                'poll_rate_hz': len(self.poll_times) / runtime if runtime > 0 else 0,
            })
            
        if runtime > 0:
            stats.update({
                'ui_update_rate_hz': self.ui_updates / runtime,
                'async_command_rate_hz': self.async_commands / runtime,
                'time_since_last_update': now - self.last_update,
            })
            
        return stats
        
    def print_stats(self):
        """Print current performance statistics"""
        stats = self.get_stats()
        
        print("\n" + "="*60)
        print("📊 PERFORMANCE MONITOR")
        print("="*60)
        print(f"⏱️  Runtime: {stats['runtime_seconds']:.1f}s")
        
        if 'avg_poll_time_ms' in stats:
            print(f"📡 Polling: {stats['avg_poll_time_ms']:.1f}ms avg, "
                  f"range {stats['min_poll_time_ms']:.1f}-{stats['max_poll_time_ms']:.1f}ms")
            print(f"📈 Poll Rate: {stats['poll_rate_hz']:.1f} Hz ({stats['poll_count']} polls)")
            
        print(f"🖥️  UI Updates: {stats['ui_updates']} ({stats.get('ui_update_rate_hz', 0):.1f} Hz)")
        print(f"🚀 Async Commands: {stats['async_commands']} ({stats.get('async_command_rate_hz', 0):.1f} Hz)")
        
        if 'time_since_last_update' in stats:
            print(f"📅 Last Update: {stats['time_since_last_update']:.1f}s ago")
            
        # Performance assessment
        if 'avg_poll_time_ms' in stats:
            if stats['avg_poll_time_ms'] < 100:
                print("✅ Polling Performance: EXCELLENT")
            elif stats['avg_poll_time_ms'] < 250:
                print("👍 Polling Performance: GOOD")
            elif stats['avg_poll_time_ms'] < 400:
                print("⚠️  Polling Performance: FAIR")
            else:
                print("❌ Polling Performance: POOR (>400ms)")
                
        print("="*60)

# Global monitor instance
monitor = PerformanceMonitor()

def start_monitor():
    """Start the performance monitor in a separate thread"""
    def monitor_loop():
        while True:
            time.sleep(10)  # Print stats every 10 seconds
            monitor.print_stats()
            
    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()
    
if __name__ == "__main__":
    print("🚀 Performance Monitor for FlowControl")
    print("This module should be imported and used within the main application")
    print("\nTo use:")
    print("1. Import: from performance_monitor import monitor")
    print("2. Log events: monitor.log_poll_time(duration_ms)")
    print("3. Start monitoring: start_monitor()")
    
    # Run a test
    start_monitor()
    
    # Simulate some events
    for i in range(20):
        monitor.log_poll_time(50 + i * 10)
        monitor.log_ui_update()
        if i % 5 == 0:
            monitor.log_async_command()
        time.sleep(0.1)
        
    monitor.print_stats()
    time.sleep(15)  # Let monitor run