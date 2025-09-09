from propar import instrument

dev = instrument('/dev/ttyUSB1', address=3, baudrate=38400)

# Get all known DDE parameters
value_24 = dev.readParameter(24)
value_25 = dev.readParameter(25)
value_60 = dev.readParameter(93)

print(f"Parameter 24 Value: {value_24} Parameter 25 value: {value_25} Parameter 93 value:{value_60}")