from propar import instrument

dev = instrument('/dev/ttyUSB1', address=3, baudrate=38400)

# Get all known DDE parameters
all_params = dev.db.get_all_parameters()

with open("parameter_log.txt", "w", encoding="utf-8") as log:
    log.write("DDE_NR | Parameter Name                          | Value           | Unit     | Type\n")
    log.write("-" * 90 + "\n")
    print("Reading all known parameters...")
    for p in all_params:
        try:
            val = dev.readParameter(p['dde_nr'])
            unit = p.get('unit', '')
            # Try to get type from parameter info, else infer from value
            param_type = p.get('type', type(val).__name__)
            log.write(f"{p['dde_nr']:>6} | {p['parm_name']:<40} = {val!s:<15} | {unit:<8} | {param_type}\n")
        except Exception as e:
            unit = p.get('unit', '')
            param_type = p.get('type', 'unknown')
            log.write(f"{p['dde_nr']:>6} | {p['parm_name']:<40} = Error: {e:<8} | {unit:<8} | {param_type}\n")
