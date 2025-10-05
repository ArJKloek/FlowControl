#!/usr/bin/env python3
"""
Test script to debug serial import issues
"""
print("Testing serial import...")

try:
    import serial
    print(f"Serial module location: {serial.__file__}")
    print(f"Serial module contents: {dir(serial)}")
    print(f"Has Serial class: {hasattr(serial, 'Serial')}")
    
    if hasattr(serial, 'Serial'):
        print("Serial class found!")
    else:
        print("ERROR: Serial class not found in serial module")
        print("This might be the wrong serial module.")
        
except ImportError as e:
    print(f"Failed to import serial: {e}")

print("\nTrying to import pyserial specifically...")
try:
    import serial.tools.list_ports
    print("pyserial tools imported successfully")
    ports = serial.tools.list_ports.comports()
    print(f"Available serial ports: {[port.device for port in ports]}")
except Exception as e:
    print(f"Failed to import pyserial tools: {e}")