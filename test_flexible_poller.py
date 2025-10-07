#!/usr/bin/env python3
"""
Test script for flexible PortPoller implementation.
Demonstrates both single-address and multi-address polling scenarios.
"""

import sys
import time
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QTextEdit, QLabel
from PyQt5.QtCore import QTimer
from backend.manager import ProparManager


class PollerTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.manager = ProparManager()
        self.setup_ui()
        
        # Connect manager signals for monitoring
        self.manager.measured.connect(self.on_measurement)
        self.manager.telemetry.connect(self.on_telemetry)
        self.manager.scanFinished.connect(self.on_scan_finished)
        
    def setup_ui(self):
        self.setWindowTitle("Flexible PortPoller Test")
        self.setGeometry(100, 100, 800, 600)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Status label
        self.status_label = QLabel("Ready to test flexible PortPoller")
        layout.addWidget(self.status_label)
        
        # Buttons
        btn_scan = QPushButton("1. Scan for Instruments")
        btn_scan.clicked.connect(self.scan_instruments)
        layout.addWidget(btn_scan)
        
        btn_auto_config = QPushButton("2. Auto-Configure Pollers")
        btn_auto_config.clicked.connect(self.auto_configure)
        layout.addWidget(btn_auto_config)
        
        btn_single = QPushButton("3. Test Single-Address Poller (COM3, Address 1)")
        btn_single.clicked.connect(self.test_single_address)
        layout.addWidget(btn_single)
        
        btn_multi = QPushButton("4. Test Multi-Address Poller (COM3, Addresses [1,2,3])")
        btn_multi.clicked.connect(self.test_multi_address)
        layout.addWidget(btn_multi)
        
        btn_stop = QPushButton("5. Stop All Pollers")
        btn_stop.clicked.connect(self.stop_pollers)
        layout.addWidget(btn_stop)
        
        # Log area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
    def log(self, message):
        """Add message to log with timestamp."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
    def scan_instruments(self):
        """Scan for available instruments."""
        self.log("Starting instrument scan...")
        self.status_label.setText("Scanning for instruments...")
        self.manager.scan()
        
    def on_scan_finished(self):
        """Handle scan completion."""
        nodes = self.manager.nodes()
        self.log(f"Scan completed. Found {len(nodes)} instruments:")
        for node in nodes:
            self.log(f"  - Port: {node.port}, Address: {node.address}, Serial: {node.serial}")
        self.status_label.setText(f"Scan complete: {len(nodes)} instruments found")
        
    def auto_configure(self):
        """Automatically configure pollers based on discovered nodes."""
        try:
            self.log("Auto-configuring pollers...")
            port_config = self.manager.auto_configure_pollers(default_period=1.0)
            
            for port, addresses in port_config.items():
                if len(addresses) == 1:
                    self.log(f"  Single-address poller: {port} -> address {addresses[0]}")
                else:
                    self.log(f"  Multi-address poller: {port} -> addresses {addresses}")
                    
            self.status_label.setText("Auto-configuration complete")
            
        except Exception as e:
            self.log(f"Auto-configuration error: {e}")
            self.status_label.setText(f"Auto-config error: {e}")
            
    def test_single_address(self):
        """Test single-address poller configuration."""
        try:
            self.log("Testing single-address poller (COM3, address 1)...")
            poller = self.manager.create_single_address_poller("COM3", 1, default_period=2.0)
            self.log(f"Single-address poller created: {len(poller.addresses)} addresses")
            self.status_label.setText("Single-address poller active")
            
        except Exception as e:
            self.log(f"Single-address test error: {e}")
            self.status_label.setText(f"Single test error: {e}")
            
    def test_multi_address(self):
        """Test multi-address poller configuration."""
        try:
            self.log("Testing multi-address poller (COM3, addresses [1,2,3])...")
            poller = self.manager.create_multi_address_poller("COM3", [1, 2, 3], default_period=1.5)
            self.log(f"Multi-address poller created: {len(poller.addresses)} addresses")
            self.status_label.setText("Multi-address poller active")
            
        except Exception as e:
            self.log(f"Multi-address test error: {e}")
            self.status_label.setText(f"Multi test error: {e}")
            
    def stop_pollers(self):
        """Stop all active pollers."""
        try:
            self.log("Stopping all pollers...")
            self.manager.stop_all_pollers()
            self.status_label.setText("All pollers stopped")
            
        except Exception as e:
            self.log(f"Stop pollers error: {e}")
            self.status_label.setText(f"Stop error: {e}")
            
    def on_measurement(self, data):
        """Handle measurement data from pollers."""
        self.log(f"Measurement: {data}")
        
    def on_telemetry(self, data):
        """Handle telemetry data from pollers."""
        if isinstance(data, dict) and data.get("kind") == "poll_result":
            port = data.get("port", "?")
            address = data.get("address", "?")
            value = data.get("value", "?")
            self.log(f"Poll result: {port}:{address} -> {value}")


def main():
    """Run the test application."""
    app = QApplication(sys.argv)
    
    window = PollerTestWindow()
    window.show()
    
    # Add periodic status updates
    timer = QTimer()
    timer.timeout.connect(lambda: None)  # Keep app responsive
    timer.start(1000)
    
    print("Flexible PortPoller Test Application Started")
    print("=" * 50)
    print("This test demonstrates:")
    print("1. Single-address polling (one instrument per USB adapter)")
    print("2. Multi-address polling (multiple instruments on RS232 bus)")
    print("3. Auto-configuration based on discovered instruments")
    print("4. Backward compatibility with existing code")
    print("=" * 50)
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()