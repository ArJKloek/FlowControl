from propar import database  # adjust import if needed

# Create a master connected to the RS485 port
#dev = instrument('/dev/ttyUSB1', address=3, baudrate=38400)

db = database()
dde_nr = 24  # for fluidset/fluidnr
param = db.get_parameter(dde_nr)
print("proc_nr:", param['proc_nr'])
print("parm_nr:", param['parm_nr'])
print("parm_type:", param['parm_type'])

# List all parameters and their descriptions
for p in db.parameters:
    print(p, db.get_parameter(p))

#from propar import instrument  # adjust import if needed

#dev = instrument('/dev/ttyUSB1', address=3, baudrate=38400)

# Read the number of fluidsets (parameter 24: 'fluidnr')
#num_fluidsets = dev.readParameter(24)
#print(f"Number of fluidsets: {num_fluidsets}")

# For each fluidset, read its name (parameter 25: 'fluidname')
#for idx in range(num_fluidsets):
#    dev.writeParameter(24, idx)  # Select fluidset index
#    name = dev.readParameter(25)  # Read fluid name
#    print(f"Fluidset {idx}: {name}")
