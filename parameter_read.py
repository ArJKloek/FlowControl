from propar import instrument

dev = instrument('/dev/ttyUSB0', address=3, baudrate=38400)

# Get all known DDE parameters
value_25 = dev.readParameter(25)
print(f"Parameter 25 value: {value_25}")