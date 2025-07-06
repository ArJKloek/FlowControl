from propar import instrument

dev = instrument('/dev/ttyUSB0', address=3, baudrate=38400)

with open("fluidsets_log.txt", "w", encoding="utf-8") as log:
    log.write("Index | Name         | Density      | FlowMin     | FlowMax     | Viscosity   \n")
    log.write("-" * 80 + "\n")
    for idx in range(8):
        try:
            dev.writeParameter(24, idx)  # Select fluidset index
            name = dev.readParameter(25)  # Fluid name
            if not name:
                log.write(f"{idx:>5} | No fluid (empty name)\n")
                break
            density = dev.readParameter(170)
            flow_min = dev.readParameter(172)
            flow_max = dev.readParameter(173)
            viscosity = dev.readParameter(171)
            log.write(f"{idx:>5} | {name:<12} | {density:<12} | {flow_min:<12} | {flow_max:<12} | {viscosity:<12}\n")
        except Exception as e:
            log.write(f"{idx:>5} | Error: {e}\n")
            break