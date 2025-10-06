#!/usr/bin/env python3
"""
Test script for the new error logging system
"""
import sys
import os
import time

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.error_logger import ErrorLogger

def test_error_logging():
    print("Testing Error Logging System...")
    
    # Create error logger
    error_logger = ErrorLogger()
    
    # Test different types of errors
    print("\n1. Testing extreme value error logging...")
    error_logger.log_extreme_value_error(
        port="DUMMY0",
        address="1", 
        extreme_value=10000000.0,
        instrument_info={
            'model': 'F-201CV',
            'serial': '12345',
            'usertag': 'Test_Instrument_1'
        }
    )
    
    print("2. Testing communication error logging...")
    error_logger.log_communication_error(
        port="COM3",
        address="2",
        error_message="Timeout during read operation",
        instrument_info={
            'model': 'F-111B',
            'serial': '67890', 
            'usertag': 'Main_Flow_Controller'
        }
    )
    
    print("3. Testing setpoint error logging...")
    error_logger.log_setpoint_error(
        port="DUMMY0",
        address="3",
        setpoint_value=50.5,
        error_message="Setpoint out of range",
        instrument_info={
            'model': 'F-201CV',
            'serial': '11111',
            'usertag': 'Secondary_Controller'
        }
    )
    
    print("4. Testing custom error logging...")
    error_logger.log_error(
        port="COM4",
        address="1",
        error_type="hardware",
        error_message="Sensor malfunction detected",
        error_details="Temperature sensor reading -999°C consistently",
        instrument_info={
            'model': 'DMFM-1234',
            'serial': '99999',
            'usertag': 'Temperature_Monitor'
        },
        measurement_data={
            'fmeasure': -999.0,
            'fsetpoint': 25.0
        }
    )
    
    # Check log files
    print(f"\n5. Checking log files...")
    log_files = error_logger.get_log_files()
    print(f"Created log files: {log_files}")
    
    if log_files:
        print(f"\nLatest log file: {log_files[-1]}")
        try:
            with open(log_files[-1], 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"Log file contents:\n{content}")
        except Exception as e:
            print(f"Error reading log file: {e}")
    
    # Test recent errors
    print(f"\n6. Testing recent errors retrieval...")
    recent = error_logger.get_recent_errors(hours=24)
    print(f"Found {len(recent)} recent errors")
    for i, error in enumerate(recent):
        print(f"  Error {i+1}: {error['error_type']} - {error['error_message']}")
    
    print("\nError logging test completed!")

if __name__ == "__main__":
    test_error_logging()