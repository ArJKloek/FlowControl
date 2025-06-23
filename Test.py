from propar import instrument

dev = instrument('/dev/ttyUSB1', address=3, baudrate=38400)

# Get all known DDE parameters
all_params = dev.db.get_all_parameters()

# Read all of them
print("Reading all known parameters...")
for p in all_params:
    try:
        val = dev.readParameter(p['dde_nr'])
        print(f"{p['dde_nr']:>4} | {p['parm_name']:<40} = {val}")
    except Exception as e:
        print(f"{p['dde_nr']:>4} | {p['parm_name']:<40} = Error: {e}")
