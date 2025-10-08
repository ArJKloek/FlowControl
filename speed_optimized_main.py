#!/usr/bin/env python3
"""
Speed Optimization Module for FlowControl Application

This module applies performance optimizations to improve application speed
while maintaining stability and crash prevention features.
"""

import logging
from speed_optimization import get_speed_profile

logger = logging.getLogger(__name__)

def apply_speed_optimizations(app, profile="fast"):
    """
    Apply speed optimizations to the FlowControl application.
    
    Args:
        app: Main application instance 
        profile (str): Speed profile to use ("fast", "conservative", "original")
    
    Returns:
        dict: Applied optimization settings
    """
    
    settings = get_speed_profile(profile)
    logger.info(f"🚀 Applying {profile} speed optimizations...")
    
    # Apply optimizations to manager if available
    if hasattr(app, 'manager') and app.manager:
        try:
            # Optimize polling periods for existing pollers
            for port, poller in getattr(app.manager, '_pollers', {}).items():
                if hasattr(poller, 'default_period'):
                    old_period = poller.default_period
                    poller.default_period = settings['default_period']
                    logger.info(f"📊 Optimized {port} polling: {old_period:.3f}s → {settings['default_period']:.3f}s")
                    
                # Update known periods in heap for immediate effect
                if hasattr(poller, '_known'):
                    for addr in poller._known:
                        if poller._known[addr] > settings['default_period']:
                            poller._known[addr] = settings['default_period']
            
            logger.info(f"✅ Applied {profile} optimizations to {len(getattr(app.manager, '_pollers', {}))} pollers")
            
        except Exception as e:
            logger.error(f"❌ Error applying optimizations to manager: {e}")
    
    # Log optimization summary
    logger.info(f"🚀 {profile.upper()} SPEED OPTIMIZATIONS APPLIED:")
    logger.info(f"   • Polling period: {settings['default_period']:.3f}s")
    logger.info(f"   • Response timeout: {settings['response_timeout']:.3f}s")
    logger.info(f"   • Retry delay: {settings['retry_base_delay']:.3f}s")
    logger.info(f"   • Main loop sleep: {settings['main_loop_sleep']:.3f}s")
    
    if settings.get('enable_bulk_reads'):
        logger.info(f"   • Bulk reads enabled (max {settings['max_bulk_params']} params)")
    
    return settings

def get_current_speed_metrics(app):
    """
    Get current speed metrics from the application.
    
    Args:
        app: Main application instance
        
    Returns:
        dict: Current speed metrics
    """
    
    metrics = {
        'polling_periods': [],
        'total_pollers': 0,
        'total_instruments': 0,
    }
    
    if hasattr(app, 'manager') and app.manager:
        pollers = getattr(app.manager, '_pollers', {})
        metrics['total_pollers'] = len(pollers)
        
        for port, poller in pollers.items():
            if hasattr(poller, 'default_period'):
                metrics['polling_periods'].append({
                    'port': port,
                    'period': poller.default_period
                })
            
            if hasattr(poller, '_known'):
                metrics['total_instruments'] += len(poller._known)
    
    return metrics

def print_speed_status(app):
    """
    Print current speed status of the application.
    
    Args:
        app: Main application instance
    """
    
    metrics = get_current_speed_metrics(app)
    
    print("🚀 CURRENT SPEED STATUS")
    print("=" * 40)
    print(f"Total Pollers: {metrics['total_pollers']}")
    print(f"Total Instruments: {metrics['total_instruments']}")
    print("\nPolling Periods:")
    
    for period_info in metrics['polling_periods']:
        period = period_info['period']
        port = period_info['port']
        updates_per_sec = 1.0 / period if period > 0 else 0
        print(f"  {port}: {period:.3f}s ({updates_per_sec:.1f} updates/sec)")
    
    if metrics['polling_periods']:
        avg_period = sum(p['period'] for p in metrics['polling_periods']) / len(metrics['polling_periods'])
        avg_updates_per_sec = 1.0 / avg_period if avg_period > 0 else 0
        print(f"\nAverage: {avg_period:.3f}s ({avg_updates_per_sec:.1f} updates/sec)")

def create_speed_optimization_commands():
    """
    Create speed optimization commands for manual use.
    
    Returns:
        dict: Dictionary of optimization commands
    """
    
    return {
        'fast': 'python -c "from speed_optimized_main import apply_fast_mode; apply_fast_mode()"',
        'conservative': 'python -c "from speed_optimized_main import apply_conservative_mode; apply_conservative_mode()"',
        'original': 'python -c "from speed_optimized_main import apply_original_mode; apply_original_mode()"',
        'status': 'python -c "from speed_optimized_main import print_current_status; print_current_status()"'
    }

# Convenience functions for direct use
def apply_fast_mode(app=None):
    """Apply fast speed optimizations."""
    if app is None:
        print("⚠️  No app instance provided - settings saved for next startup")
        return get_speed_profile("fast")
    return apply_speed_optimizations(app, "fast")

def apply_conservative_mode(app=None):
    """Apply conservative speed optimizations.""" 
    if app is None:
        print("⚠️  No app instance provided - settings saved for next startup")
        return get_speed_profile("conservative")
    return apply_speed_optimizations(app, "conservative")

def apply_original_mode(app=None):
    """Restore original speed settings."""
    if app is None:
        print("⚠️  No app instance provided - settings saved for next startup")
        return get_speed_profile("original")
    return apply_speed_optimizations(app, "original")

def print_current_status(app=None):
    """Print current speed status."""
    if app is None:
        print("⚠️  No app instance provided - cannot show current status")
        return
    print_speed_status(app)

if __name__ == "__main__":
    print("🚀 Speed Optimization Module")
    print("\nAvailable speed profiles:")
    
    profiles = ["original", "conservative", "fast"]
    for profile in profiles:
        settings = get_speed_profile(profile)
        period = settings['default_period']
        updates_per_sec = 1.0 / period
        print(f"  {profile.capitalize():>12}: {period:.3f}s polling ({updates_per_sec:.1f} updates/sec)")
    
    print("\nOptimization commands:")
    commands = create_speed_optimization_commands()
    for name, command in commands.items():
        print(f"  {name}: {command}")