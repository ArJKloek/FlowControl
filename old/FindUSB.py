import glob

# List all ttyUSB devices
usb_devices = glob.glob('/dev/ttyUSB*')

# Print the devices and their count
print("Found ttyUSB devices:")
for dev in usb_devices:
    print(dev)
print(f"Total ttyUSB devices: {len(usb_devices)}")