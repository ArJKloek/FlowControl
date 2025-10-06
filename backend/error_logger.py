import os
import csv
import time
from datetime import datetime
from typing import Optional, Dict, Any
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
import threading

class ErrorLogger(QObject):
    """
    Dedicated error logger for instrument-specific errors.
    Logs errors to CSV files with instrument details and timestamps.
    """
    
    error_logged = pyqtSignal(str)  # Emitted when an error is successfully logged
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create error log directory
        self.log_dir = os.path.join(os.getcwd(), "ErrorLogs")
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Current log file (rotated daily)
        self._current_log_file = None
        self._current_date = None
        self._lock = threading.Lock()
        
        # CSV fieldnames
        self.fieldnames = [
            'timestamp',
            'date',
            'time', 
            'port',
            'address',
            'instrument_model',
            'instrument_serial',
            'instrument_usertag',
            'error_type',
            'error_message',
            'error_details',
            'measurement_value',
            'setpoint_value'
        ]
    
    def _get_log_file_path(self) -> str:
        """Get the current log file path, creating a new one if date changed."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if today != self._current_date:
            self._current_date = today
            self._current_log_file = os.path.join(
                self.log_dir, 
                f"instrument_errors_{today}.csv"
            )
            
            # Create file with headers if it doesn't exist
            if not os.path.exists(self._current_log_file):
                try:
                    with open(self._current_log_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                        writer.writeheader()
                except Exception as e:
                    print(f"Error creating error log file: {e}")
        
        return self._current_log_file
    
    @pyqtSlot(str, str, str, str, str)
    @pyqtSlot(str, str, str, str, str, dict)
    def log_error(self, 
                  port: str, 
                  address: str, 
                  error_type: str, 
                  error_message: str, 
                  error_details: str = "",
                  instrument_info: Optional[Dict[str, Any]] = None,
                  measurement_data: Optional[Dict[str, Any]] = None):
        """
        Log an instrument error to CSV file.
        
        Args:
            port: Instrument port (e.g., 'COM3', 'DUMMY0')
            address: Instrument address (e.g., '1', '2', '3')
            error_type: Type of error ('communication', 'measurement', 'setpoint', 'validation', 'hardware')
            error_message: Brief error description
            error_details: Detailed error information
            instrument_info: Dict with instrument details (model, serial, usertag)
            measurement_data: Dict with measurement context (fmeasure, setpoint, etc.)
        """
        
        with self._lock:
            try:
                now = datetime.now()
                
                # Extract instrument info
                if instrument_info is None:
                    instrument_info = {}
                
                # Extract measurement data  
                if measurement_data is None:
                    measurement_data = {}
                
                log_entry = {
                    'timestamp': now.isoformat(),
                    'date': now.strftime("%Y-%m-%d"),
                    'time': now.strftime("%H:%M:%S.%f")[:-3],  # Include milliseconds
                    'port': str(port),
                    'address': str(address),
                    'instrument_model': str(instrument_info.get('model', '')),
                    'instrument_serial': str(instrument_info.get('serial', '')),
                    'instrument_usertag': str(instrument_info.get('usertag', '')),
                    'error_type': str(error_type),
                    'error_message': str(error_message),
                    'error_details': str(error_details),
                    'measurement_value': str(measurement_data.get('fmeasure', '')),
                    'setpoint_value': str(measurement_data.get('fsetpoint', ''))
                }
                
                log_file = self._get_log_file_path()
                if log_file:
                    with open(log_file, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                        writer.writerow(log_entry)
                    
                    # Emit signal for UI feedback
                    self.error_logged.emit(f"Error logged: {error_type} - {error_message}")
                    
            except Exception as e:
                print(f"Failed to log error: {e}")
    
    def log_extreme_value_error(self, port: str, address: str, extreme_value: float, 
                               instrument_info: Optional[Dict[str, Any]] = None):
        """Convenience method for logging extreme value errors."""
        self.log_error(
            port=port,
            address=address, 
            error_type="validation",
            error_message="Extreme measurement value detected",
            error_details=f"Measurement value {extreme_value} exceeds normal range (>= 1,000,000)",
            instrument_info=instrument_info,
            measurement_data={'fmeasure': extreme_value}
        )
    
    def log_communication_error(self, port: str, address: str, error_message: str,
                               instrument_info: Optional[Dict[str, Any]] = None):
        """Convenience method for logging communication errors."""
        self.log_error(
            port=port,
            address=address,
            error_type="communication", 
            error_message="Instrument communication failed",
            error_details=error_message,
            instrument_info=instrument_info
        )
    
    def log_setpoint_error(self, port: str, address: str, setpoint_value: float, error_message: str,
                          instrument_info: Optional[Dict[str, Any]] = None):
        """Convenience method for logging setpoint errors."""
        self.log_error(
            port=port,
            address=address,
            error_type="setpoint",
            error_message="Setpoint operation failed", 
            error_details=error_message,
            instrument_info=instrument_info,
            measurement_data={'fsetpoint': setpoint_value}
        )
    
    def get_log_files(self) -> list:
        """Get list of all error log files."""
        try:
            files = []
            for filename in os.listdir(self.log_dir):
                if filename.startswith("instrument_errors_") and filename.endswith(".csv"):
                    filepath = os.path.join(self.log_dir, filename)
                    files.append(filepath)
            return sorted(files)
        except Exception:
            return []
    
    def get_recent_errors(self, hours: int = 24) -> list:
        """Get recent errors from the current log file."""
        try:
            log_file = self._get_log_file_path()
            if not os.path.exists(log_file):
                return []
            
            cutoff_time = time.time() - (hours * 3600)
            recent_errors = []
            
            with open(log_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # Parse timestamp
                        error_time = datetime.fromisoformat(row['timestamp']).timestamp()
                        if error_time >= cutoff_time:
                            recent_errors.append(row)
                    except Exception:
                        continue
            
            return recent_errors
            
        except Exception as e:
            print(f"Error reading recent errors: {e}")
            return []