# Import the propar module
import propar

# Connect to the local instrument.
#el_flow = propar.instrument('COM1')
el_flow = propar.instrument('/dev/ttyUSB0', address=6, baudrate=38400)

# Prepare a list of parameters for a chained read containing:
# fmeasure, fsetpoint, temperature, valve output
params = [{'proc_nr':  33, 'parm_nr': 0, 'parm_type': propar.PP_TYPE_FLOAT},
          {'proc_nr':  33, 'parm_nr': 3, 'parm_type': propar.PP_TYPE_FLOAT},
          {'proc_nr':  33, 'parm_nr': 7, 'parm_type': propar.PP_TYPE_FLOAT},
          {'proc_nr': 114, 'parm_nr': 1, 'parm_type': propar.PP_TYPE_INT32}]

# Note that this uses the read_parameters function.
values = el_flow.read_parameters(params)

# Display the values returned by the read_parameters function. A single 'value' includes
# the original fields of the parameters supplied to the request, with the data stored in
# the value['data'] field.
for value in values:
  print(value)

# For writes the parameter must have the 'data' field set with the value to write when
# passing it to the write_parameters function.
#params = [{'proc_nr': 1, 'parm_nr': 1, 'parm_type': propar.PP_TYPE_INT16, 'data': 32000}]

# Write parameters returns a propar status code.
#status = el_flow.write_parameters(params)

# Also, note that when using the master directly the address of the node must be set in the
# parameter object that is passed to the read_parameters or write_parameters function
#params = [{'node': 3, 'proc_nr': 1, 'parm_nr': 1, 'parm_type': propar.PP_TYPE_INT16}]

# Read from the master directly
#values = el_flow.master.read_parameters(params)