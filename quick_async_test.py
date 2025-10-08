#!/usr/bin/env python3
"""
Quick test to trigger async commands and see debug output
"""

import time
import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.manager import ProparManager

def main():
    print("🧪 Quick Async Command Test")
    print("=" * 50)
    
    # Create manager (this should start pollers if instruments are available)
    manager = ProparManager()
    
    # Give it a moment to initialize
    time.sleep(2)
    
    print(f"📋 Active pollers: {list(manager._pollers.keys())}")
    
    # Try to trigger an async command on the first available port/address
    if manager._pollers:
        port = list(manager._pollers.keys())[0]
        print(f"🎯 Testing async command on port: {port}")
        
        # Try a simple async setpoint change
        try:
            print("🚀 Triggering async setpoint change...")
            manager.request_setpoint_flow(port, 3, 25.0)  # This should now call async method
            
            print("⏱️  Waiting 3 seconds to see async debug output...")
            time.sleep(3)
            
            print("🚀 Triggering async percentage change...")
            manager.request_setpoint_pct(port, 3, 50.0)  # This should now call async method
            
            print("⏱️  Waiting 3 seconds to see async debug output...")
            time.sleep(3)
            
        except Exception as e:
            print(f"❌ Error triggering async command: {e}")
    else:
        print("❌ No active pollers found - make sure instruments are connected")
    
    print("\n✅ Test complete - check output above for async debug messages")
    print("Expected output format:")
    print("  🚀 ASYNC DEBUG: 📤 Started async_fset_flow...")
    print("  🚀 ASYNC DEBUG: ✅ Reply received for async_fset_flow in XX.XXms")

if __name__ == "__main__":
    main()