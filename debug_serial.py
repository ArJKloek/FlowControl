#!/usr/bin/env python3
"""
Comprehensive serial import debugging
"""
import sys
import os

print("Python version:", sys.version)
print("Current working directory:", os.getcwd())
print("Python path:")
for p in sys.path:
    print(f"  {p}")

print("\n" + "="*50)
print("Testing serial imports...")

# Test 1: Basic import
try:
    import serial
    print(f"✓ 'import serial' succeeded")
    print(f"  Location: {getattr(serial, '__file__', 'No __file__ attribute')}")
    print(f"  Package: {getattr(serial, '__package__', 'No __package__ attribute')}")
    print(f"  Has Serial: {hasattr(serial, 'Serial')}")
except Exception as e:
    print(f"✗ 'import serial' failed: {e}")

# Test 2: Direct Serial import
try:
    from serial import Serial
    print(f"✓ 'from serial import Serial' succeeded: {Serial}")
except Exception as e:
    print(f"✗ 'from serial import Serial' failed: {e}")

# Test 3: Check installed packages
print("\n" + "="*50)
print("Checking installed packages...")
try:
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pip", "list"], 
                          capture_output=True, text=True)
    lines = result.stdout.split('\n')
    serial_packages = [line for line in lines if 'serial' in line.lower()]
    print("Serial-related packages:")
    for pkg in serial_packages:
        print(f"  {pkg}")
except Exception as e:
    print(f"Failed to check packages: {e}")

# Test 4: Manual path check
print("\n" + "="*50)
print("Manual serial module search...")
for path in sys.path:
    serial_path = os.path.join(path, 'serial')
    if os.path.exists(serial_path):
        print(f"Found serial module at: {serial_path}")
        if os.path.isdir(serial_path):
            print(f"  Contents: {os.listdir(serial_path)[:10]}...")  # First 10 items
        
# Test 5: Try alternative import method
print("\n" + "="*50)
print("Testing alternative import methods...")
try:
    import importlib
    serial_module = importlib.import_module('serial')
    print(f"✓ importlib.import_module('serial') succeeded")
    
    # Try to get Serial class
    if hasattr(serial_module, 'Serial'):
        print(f"✓ Serial class found via importlib")
    else:
        # Maybe it's in a submodule?
        try:
            serial_serial = importlib.import_module('serial.serialposix')  # Linux/Mac
            print(f"✓ Found serial.serialposix")
        except:
            try:
                serial_serial = importlib.import_module('serial.serialwin32')  # Windows
                print(f"✓ Found serial.serialwin32")
            except Exception as e2:
                print(f"✗ Could not find Serial class in submodules: {e2}")
                
except Exception as e:
    print(f"✗ importlib approach failed: {e}")