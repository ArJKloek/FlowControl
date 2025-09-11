from propar import instrument

dev = instrument('/dev/ttyUSB0', address=3, baudrate=38400)


dev.writeParameter(24, 1)  # Select fluidset index
name = dev.readParameter(25)  # Fluid name
density = dev.readParameter(170)
flow_max = dev.readParameter(21)
viscosity = dev.readParameter(252)
capacity = dev.readParameter(21)  # Assuming capacity is at DDE 129
unit = dev.readParameter(129)
print(f"Name: {name}, Density: {density}, Flow Max: {flow_max}, Viscosity: {viscosity}, Capacity: {capacity}, Unit: {unit}")
