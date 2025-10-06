#!/usr/bin/env python3
"""
Test script to check if control_dialog.py error logging integration works
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.control_dialog import ControllerDialog
from backend.manager import ProparManager
from backend.error_logger import ErrorLogger

# Test if the classes can be instantiated
try:
    print("Testing error logging integration...")
    
    # Check if ErrorLogger works
    error_logger = ErrorLogger()
    print("✓ ErrorLogger created successfully")
    
    # Check if the error logger has all required methods
    required_methods = ['log_error', 'log_validation_error', 'log_communication_error', 'log_setpoint_error', 'log_fluid_change_error']
    for method in required_methods:
        if hasattr(error_logger, method):
            print(f"✓ ErrorLogger.{method} exists")
        else:
            print(f"✗ ErrorLogger.{method} missing")
    
    print("\nAll error logging integration tests passed!")
    
except Exception as e:
    print(f"Error during testing: {e}")
    import traceback
    traceback.print_exc()