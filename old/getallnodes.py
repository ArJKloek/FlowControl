import glob
from propar import master  # adjust import if needed

# List all ttyUSB devices
usb_devices = glob.glob('/dev/ttyUSB*')

for usb in usb_devices:
    print(f"\nScanning {usb}...")
    try:
        m = master(usb, baudrate=38400)
        nodes = m.get_nodes()
        if nodes:
            print("Found devices:")
            for node in nodes:
                print(f"Address: {node['address']}, Type: {node['type']}, Serial: {node['serial']}, ID: {node['id']}, Channels: {node['channels']}")
        else:
            print("No devices found.")
    except Exception as e:
        print(f"Error scanning {usb}: {e}")