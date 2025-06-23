from propar import database  # adjust import if needed

# Create a master connected to the RS485 port
#dev = instrument('/dev/ttyUSB1', address=3, baudrate=38400)

db = database()
dde_nr = 24  # for fluidset/fluidnr
param = db.get_parameter(dde_nr)
print("proc_nr:", param['proc_nr'])
print("parm_nr:", param['parm_nr'])
print("parm_type:", param['parm_type'])

from propar import instrument  # adjust import if needed

#Create a master connected to the RS485 port
dev = instrument('/dev/ttyUSB1', address=3, baudrate=38400)

data = dev.read(1, 16,0)

print(len(data))
