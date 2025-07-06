from propar import instrument

dev = instrument('/dev/ttyUSB1', address=3, baudrate=38400)

with open("fluidsets_log.txt", "w", encoding="utf-8") as log:
    log.write("Index | Name         | Density      | ...\n")
    log.write("-" * 50 + "\n")
    for idx in range(10):
        try:
            dev.writeParameter(24, idx)  # Select fluidset index
            name = dev.readParameter(25)  # Fluid name
            if not name:  # Stop if name is empty or None
                log.write(f"{idx:>5} | No fluid (empty name)\n")
                break
            density = dev.readParameter(170)  # Density (if available)
            log.write(f"{idx:>5} | {name:<12} | {density:<12}\n")
        except Exception as e:
            log.write(f"{idx:>5} | Error: {e}\n")
            break