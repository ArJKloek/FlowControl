import propar

el_flow = propar.instrument('/dev/ttyUSB0', address=6, baudrate=38400)

params = [
    {'proc_nr': 1, 'parm_nr': 24, 'parm_type': propar.PP_TYPE_INT16},   # Fluid index
    {'proc_nr': 1, 'parm_nr': 25, 'parm_type': propar.PP_TYPE_STRING},  # Fluid name
    {'proc_nr': 1, 'parm_nr': 170, 'parm_type': propar.PP_TYPE_FLOAT},  # Density
    {'proc_nr': 1, 'parm_nr': 172, 'parm_type': propar.PP_TYPE_FLOAT},  # Flow min
    {'proc_nr': 1, 'parm_nr': 173, 'parm_type': propar.PP_TYPE_FLOAT},  # Flow max
    {'proc_nr': 1, 'parm_nr': 171, 'parm_type': propar.PP_TYPE_FLOAT},  # Viscosity
]

values = el_flow.read_parameters(params)

for value in values:
    print(f"Parameter {value['parm_nr']}: {value['data']}")