import propar
import sys
import glob
import time
import argparse
from datetime import datetime

MEASURE_INTERVAL = 0.5  # seconds between measurements
DEFAULT_BENCHMARK_PARAMETERS = [8, 9, 11]


def find_usb_serial_ports():
    """Return a list of likely USB serial ports on Linux/Raspberry Pi."""
    candidates = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    return sorted(candidates)


def safe_read_parameter(instrument, dde_number):
    try:
        return instrument.readParameter(dde_number)
    except Exception:
        return None


def format_multi_response(response, dde_numbers):
    values = []
    for dde_number, entry in zip(dde_numbers, response):
        values.append(f"p{dde_number}={entry.get('data')!r}")
    return ", ".join(values)


def scan_port(comport):
    """Scan a single port and return a list of instrument instances with metadata."""
    instruments = []
    print(f"\n  Scanning {comport}...")
    try:
        local = propar.instrument(comport)
        nodes = local.master.get_nodes()

        if not nodes:
            print(f"  No instruments found on {comport}.")
            return instruments

        print(f"  Found {len(nodes)} node(s) on {comport}:")
        for node in nodes:
            address  = node['address']
            channels = node.get('channels', 1)
            dev_type = node.get('type', 'Unknown')
            serial   = node.get('serial', 'Unknown')
            print(f"    Address={address}  Type={dev_type}  Serial={serial}  Channels={channels}")

            for ch in range(1, channels + 1):
                instr = propar.instrument(comport, address=address, channel=ch)
                tag = safe_read_parameter(instr, 115)  # User tag
                label = tag if tag else f"Node{address}"
                if channels > 1:
                    label += f"-ch{ch}"

                model = safe_read_parameter(instr, 91)       # BHT model number
                firmware = safe_read_parameter(instr, 105)   # Firmware version
                fluid = safe_read_parameter(instr, 25)       # Fluid name
                unit = safe_read_parameter(instr, 129)       # Capacity/readout unit
                setpoint = safe_read_parameter(instr, 9)     # Setpoint (0..32000)
                measure = safe_read_parameter(instr, 8)      # Measure (0..32000)

                instruments.append({
                    'instrument': instr,
                    'label':      label,
                    'port':       comport,
                    'address':    address,
                    'channel':    ch,
                })
                print(f"      ch{ch}: label={label!r}")
                print(f"        model={model!r}  firmware={firmware!r}")
                print(f"        fluid={fluid!r}  unit={unit!r}")
                print(f"        setpoint={setpoint!r}  measure={measure!r}")

    except Exception as e:
        print(f"  Error scanning {comport}: {e}")

    return instruments


def measure_loop(instruments):
    """Continuously read and print measurements from all instruments."""
    print("\n" + "=" * 70)
    print("Starting continuous measurement. Press Ctrl+C to stop.")
    print("=" * 70)

    # Build header
    labels = [i['label'] for i in instruments]
    col_w  = max(len(l) for l in labels + ['Timestamp']) + 2
    header = f"{'Timestamp':<22}" + "".join(f"{l:>{col_w}}" for l in labels)
    print(header)
    print("-" * len(header))

    while True:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        row = f"{timestamp:<22}"
        for item in instruments:
            try:
                value = item['instrument'].measure
                row += f"{str(value):>{col_w}}"
            except Exception:
                row += f"{'ERR':>{col_w}}"
        print(row)
        time.sleep(MEASURE_INTERVAL)


def benchmark_loop(instruments, duration_seconds):
    """Benchmark maximum read speed by polling measure as fast as possible."""
    print("\n" + "=" * 70)
    print(f"Starting benchmark for {duration_seconds:.1f} seconds...")
    print("=" * 70)

    if duration_seconds <= 0:
        print("Benchmark duration must be greater than 0.")
        return

    per_instrument_reads = {item['label']: 0 for item in instruments}
    per_instrument_errors = {item['label']: 0 for item in instruments}
    last_values = {item['label']: None for item in instruments}

    total_reads = 0
    total_errors = 0
    started = time.perf_counter()

    while True:
        now = time.perf_counter()
        if (now - started) >= duration_seconds:
            break

        for item in instruments:
            label = item['label']
            try:
                value = item['instrument'].measure
                per_instrument_reads[label] += 1
                last_values[label] = value
                total_reads += 1
            except Exception:
                per_instrument_errors[label] += 1
                total_errors += 1

    elapsed = time.perf_counter() - started
    if elapsed <= 0:
        elapsed = 1e-9

    print(f"Elapsed time: {elapsed:.3f} s")
    print(f"Total successful reads: {total_reads}")
    print(f"Total read errors: {total_errors}")
    print(f"Total read rate: {total_reads / elapsed:.2f} reads/s")
    print("\nPer instrument:")

    for item in instruments:
        label = item['label']
        reads = per_instrument_reads[label]
        errors = per_instrument_errors[label]
        print(f"  {label}: {reads / elapsed:.2f} reads/s ({reads} ok, {errors} errors)")

    print("\nLast successful read values:")
    for item in instruments:
        label = item['label']
        print(f"  {label}: measure={last_values[label]!r}")


def build_parameter_list(instrument, dde_numbers):
    return [instrument.db.get_parameter(dde_number) for dde_number in dde_numbers]


def benchmark_multi_read_loop(instruments, duration_seconds, dde_numbers):
    """Benchmark chained read_parameters cycles with multiple DDE parameters."""
    print("\n" + "=" * 70)
    print(f"Starting multi-parameter benchmark for {duration_seconds:.1f} seconds...")
    print(f"Parameters per cycle: {', '.join(str(p) for p in dde_numbers)}")
    print("=" * 70)

    if duration_seconds <= 0:
        print("Benchmark duration must be greater than 0.")
        return

    per_instrument_cycles = {item['label']: 0 for item in instruments}
    per_instrument_errors = {item['label']: 0 for item in instruments}
    last_values = {item['label']: None for item in instruments}
    parameter_lists = {}

    for item in instruments:
        try:
            parameter_lists[item['label']] = build_parameter_list(item['instrument'], dde_numbers)
        except Exception as exc:
            print(f"Could not prepare parameters for {item['label']}: {exc}")
            return

    total_cycles = 0
    total_parameter_reads = 0
    total_errors = 0
    started = time.perf_counter()

    while True:
        now = time.perf_counter()
        if (now - started) >= duration_seconds:
            break

        for item in instruments:
            label = item['label']
            try:
                response = item['instrument'].read_parameters(parameter_lists[label])
                if response and all('data' in entry for entry in response):
                    per_instrument_cycles[label] += 1
                    last_values[label] = response
                    total_cycles += 1
                    total_parameter_reads += len(response)
                else:
                    per_instrument_errors[label] += 1
                    total_errors += 1
            except Exception:
                per_instrument_errors[label] += 1
                total_errors += 1

    elapsed = time.perf_counter() - started
    if elapsed <= 0:
        elapsed = 1e-9

    print(f"Elapsed time: {elapsed:.3f} s")
    print(f"Total successful cycles: {total_cycles}")
    print(f"Total parameter values read: {total_parameter_reads}")
    print(f"Total cycle errors: {total_errors}")
    print(f"Total cycle rate: {total_cycles / elapsed:.2f} cycles/s")
    print(f"Total parameter rate: {total_parameter_reads / elapsed:.2f} values/s")
    print("\nPer instrument:")

    for item in instruments:
        label = item['label']
        cycles = per_instrument_cycles[label]
        errors = per_instrument_errors[label]
        print(
            f"  {label}: {cycles / elapsed:.2f} cycles/s "
            f"({cycles * len(dde_numbers) / elapsed:.2f} values/s, {cycles} ok, {errors} errors)"
        )

    print("\nLast successful read values:")
    for item in instruments:
        label = item['label']
        response = last_values[label]
        if response is None:
            print(f"  {label}: no successful response")
        else:
            print(f"  {label}: {format_multi_response(response, dde_numbers)}")


# ── Main ──────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Scan Propar instruments and either stream measurements or run a speed benchmark."
)
parser.add_argument(
    'ports',
    nargs='*',
    help="Serial ports to scan, e.g. /dev/ttyUSB0 /dev/ttyUSB1",
)
parser.add_argument(
    '--benchmark',
    action='store_true',
    help="Run speed benchmark instead of continuous measurement display.",
)
parser.add_argument(
    '--benchmark-seconds',
    type=float,
    default=10.0,
    help="Benchmark duration in seconds (default: 10).",
)
parser.add_argument(
    '--benchmark-mode',
    choices=['single', 'multi'],
    default='single',
    help="Benchmark single measure reads or chained multi-parameter read_parameters cycles.",
)
parser.add_argument(
    '--benchmark-params',
    type=int,
    nargs='+',
    default=DEFAULT_BENCHMARK_PARAMETERS,
    help="DDE parameters to use in multi benchmark mode (default: 8 9 11).",
)
parser.add_argument(
    '--interval',
    type=float,
    default=MEASURE_INTERVAL,
    help=f"Continuous mode update interval in seconds (default: {MEASURE_INTERVAL}).",
)
args = parser.parse_args()

if args.ports:
    ports = args.ports
else:
    ports = find_usb_serial_ports()
    if not ports:
        print("No USB serial ports found. Trying COM1 as fallback.")
        ports = ['COM1']

print(f"USB serial port(s) to scan: {', '.join(ports)}")

all_instruments = []
for port in ports:
    all_instruments.extend(scan_port(port))

if not all_instruments:
    print("\nNo instruments found on any port. Exiting.")
    sys.exit(1)

print(f"\nTotal instruments found: {len(all_instruments)}")

try:
    MEASURE_INTERVAL = args.interval
    if args.benchmark:
        if args.benchmark_mode == 'multi':
            benchmark_multi_read_loop(all_instruments, args.benchmark_seconds, args.benchmark_params)
        else:
            benchmark_loop(all_instruments, args.benchmark_seconds)
    else:
        measure_loop(all_instruments)
except KeyboardInterrupt:
    print("\nMeasurement stopped.")
