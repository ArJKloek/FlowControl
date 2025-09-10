from propar import instrument
import collections.abc

dev = instrument('/dev/ttyUSB1', address=3)

all_params = dev.db.get_all_parameters()

with open("list_parameters_log_DMFM.txt", "w", encoding="utf-8") as log:
    log.write("DDE_NR | Parameter Name                          | Type         | Value (truncated)\n")
    log.write("-" * 100 + "\n")
    print("Testing all parameters for list-like values...")
    for p in all_params:
        try:
            val = dev.readParameter(p['dde_nr'])
            # Check if value is a list/tuple/set (but not string/bytes)
            if isinstance(val, collections.abc.Iterable) and not isinstance(val, (str, bytes, dict)):
                param_type = p.get('type', type(val).__name__)
                log.write(f"{p['dde_nr']:>6} | {p['parm_name']:<40} | {param_type:<12} | {str(val)[:50]}\n")
                print(f"List-like: {p['dde_nr']} - {p['parm_name']}")
        except Exception as e:
            continue