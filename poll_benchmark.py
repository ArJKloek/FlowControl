#!/usr/bin/env python3
import argparse
import glob
import statistics
import sys
import threading
import time
from typing import Dict, List, Tuple

# External lib you already use
from propar_new import master as ProparMaster, instrument as ProparInstrument

DEFAULT_BAUD = 38400
DEFAULT_DDES = [205]  # fMeasure
USB_PATTERNS = ['/dev/ttyUSB*']  # simple default scan

def find_ports(patterns: List[str]) -> List[str]:
    found = []
    for pat in patterns:
        found.extend(glob.glob(pat))
    # de-duplicate while preserving order
    seen = set()
    ordered = []
    for f in found:
        if f not in seen:
            ordered.append(f)
            seen.add(f)
    return ordered

def discover_nodes(ports: List[str], baudrate: int) -> Dict[str, List[int]]:
    mapping: Dict[str, List[int]] = {}
    for port in ports:
        try:
            m = ProparMaster(port, baudrate=baudrate)
            nodes = m.get_nodes() or []
            mapping[port] = [int(n['address']) for n in nodes]
            try:
                m.close()
            except Exception:
                pass
        except Exception as e:
            print(f"[WARN] Could not open {port}: {e}", file=sys.stderr)
    return mapping

def _ok_result_list(res_list) -> bool:
    if not isinstance(res_list, (list, tuple)) or not res_list:
        return False
    for r in res_list:
        if not (isinstance(r, dict) and r.get('status', 1) == 0 and r.get('data', None) is not None):
            return False
    return True

def poll_worker(port: str,
                address: int,
                baudrate: int,
                ddes: List[int],
                duration: float,
                start_event: threading.Event,
                results: Dict[Tuple[str, int], dict],
                target_period: float = None,
                resp_timeout: float = 0.08,
                byte_timeout: float = 0.005):
    # Prepare instrument + cached params
    inst = ProparInstrument(port, address=address, baudrate=baudrate)
    inst.master.response_timeout = float(resp_timeout)
    try:
        # Some transports expose underlying serial timeout
        inst.master.propar.serial.timeout = float(byte_timeout)
    except Exception:
        pass

    params = inst.db.get_parameters(ddes)

    # Warm-up read (populate caches, etc.)
    try:
        _ = inst.read_parameters(params)
    except Exception:
        pass

    # Synchronize start
    start_event.wait()

    end_t = time.perf_counter() + duration
    t_prev = None
    dts = []
    successes = 0
    errors = 0
    read_latencies = []

    while time.perf_counter() < end_t:
        t0 = time.perf_counter()
        try:
            res = inst.read_parameters(params) or []
            ok = _ok_result_list(res)
            if ok:
                successes += 1
                t1 = time.perf_counter()
                read_latencies.append(t1 - t0)
                if t_prev is not None:
                    dts.append(t0 - t_prev)
                t_prev = t0
            else:
                errors += 1
        except Exception:
            errors += 1

        if target_period is not None:
            elapsed = time.perf_counter() - t0
            sleep_for = target_period - elapsed
            if sleep_for > 0:
                # cap sleep quantum to keep responsiveness
                time.sleep(min(sleep_for, 0.02))

    # Summarize
    def _summ(vals):
        if not vals:
            return {"count": 0, "mean": None, "p95": None, "min": None, "max": None}
        vals_sorted = sorted(vals)
        p95 = vals_sorted[int(0.95 * (len(vals_sorted)-1))]
        return {
            "count": len(vals),
            "mean": sum(vals) / len(vals),
            "p95": p95,
            "min": vals_sorted[0],
            "max": vals_sorted[-1],
        }

    results[(port, address)] = {
        "successes": successes,
        "errors": errors,
        "intervals": _summ(dts),
        "latencies": _summ(read_latencies),
        "duration": duration,
        "target_period": target_period,
    }

def human_rate(n_ok: int, duration: float) -> str:
    if duration <= 0:
        return "n/a"
    r = n_ok / duration
    if r >= 1000:
        return f"{r:,.0f} Hz"
    return f"{r:,.1f} Hz"

def human_time(s: float) -> str:
    if s is None:
        return "n/a"
    if s < 1e-3:
        return f"{s*1e6:.0f} µs"
    if s < 1.0:
        return f"{s*1e3:.1f} ms"
    return f"{s:.3f} s"

def main():
    ap = argparse.ArgumentParser(description="Poll-rate benchmark for Bronkhorst/PROPAR instruments (one per USB).")
    ap.add_argument("--ports", default="", help="Comma-separated list of ports. If empty, auto-scan /dev/ttyUSB*.")
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="Baudrate (default 38400).")
    ap.add_argument("--addresses", default="", help="Optional comma-separated addresses matching the ports list.")
    ap.add_argument("--ddes", default="205", help="Comma-separated DDEs to read each cycle (default '205' = fMeasure).")
    ap.add_argument("--duration", type=float, default=10.0, help="Seconds per run (default 10).")
    ap.add_argument("--mode", choices=["free", "periodic"], default="free",
                    help="'free' = as fast as possible; 'periodic' = enforce --period per cycle.")
    ap.add_argument("--period", type=float, default=0.05, help="Target period in seconds when --mode periodic (default 0.05).")
    ap.add_argument("--resp-timeout", type=float, default=0.08, help="Master response timeout (default 0.08).")
    ap.add_argument("--byte-timeout", type=float, default=0.005, help="Underlying serial byte timeout if available (default 0.005).")

    args = ap.parse_args()

    # Resolve ports
    if args.ports.strip():
        ports = [p.strip() for p in args.ports.split(",") if p.strip()]
    else:
        ports = find_ports(USB_PATTERNS)
        if not ports:
            print("No ports found. Provide --ports or attach devices.", file=sys.stderr)
            sys.exit(2)

    # Resolve addresses (optional)
    addr_map: Dict[str, List[int]] = {}
    if args.addresses.strip():
        addrs = [int(a.strip()) for a in args.addresses.split(",") if a.strip()]
        if len(addrs) != len(ports):
            print("If you pass --addresses, it must have the same count as --ports.", file=sys.stderr)
            sys.exit(2)
        for p, a in zip(ports, addrs):
            addr_map[p] = [a]
    else:
        # Discover nodes per port
        print("Discovering nodes...", file=sys.stderr)
        addr_map = discover_nodes(ports, args.baud)
        for p in list(addr_map.keys()):
            if not addr_map[p]:
                print(f"[WARN] No nodes found on {p}; skipping.", file=sys.stderr)
                addr_map.pop(p, None)

    if not addr_map:
        print("No ports with nodes to test.", file=sys.stderr)
        sys.exit(1)

    ddes = [int(x.strip()) for x in args.ddes.split(",") if x.strip()]
    duration = float(args.duration)
    target_period = (args.period if args.mode == "periodic" else None)

    # Launch workers: one per (port, first-address)
    start_event = threading.Event()
    threads = []
    results: Dict[Tuple[str, int], dict] = {}

    for port, addrs in addr_map.items():
        # You said 1 instrument per USB; pick the first node we found
        address = int(addrs[0])
        t = threading.Thread(
            target=poll_worker,
            args=(port, address, args.baud, ddes, duration, start_event, results, target_period, args.resp_timeout, args.byte_timeout),
            daemon=True
        )
        threads.append(t)

    print(f"Starting benchmark for {len(threads)} instrument(s) for {duration:.1f}s (mode={args.mode}, target_period={target_period})...")
    for t in threads:
        t.start()
    t0 = time.perf_counter()
    start_event.set()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0

    # Report
    print("\n=== Poll benchmark results ===")
    for (port, address), r in results.items():
        succ = r["successes"]
        errs = r["errors"]
        lat = r["latencies"]
        ints = r["intervals"]
        eff_rate = human_rate(succ, r["duration"])
        print(f"\n[{port} addr {address}]  {eff_rate}  |  ok={succ} err={errs}")
        if target_period is not None:
            print(f"  target period: {human_time(target_period)}  (target rate {1.0/target_period:.1f} Hz)")
        print(f"  read latency: mean={human_time(lat['mean'])}, p95={human_time(lat['p95'])}, min={human_time(lat['min'])}, max={human_time(lat['max'])}")
        if ints["count"] > 0:
            print(f"  inter-arrival: mean={human_time(ints['mean'])}, p95={human_time(ints['p95'])}, min={human_time(ints['min'])}, max={human_time(ints['max'])}")
            if target_period is not None:
                # Jitter vs target
                jitter = abs(ints['mean'] - target_period) if ints['mean'] is not None else None
                print(f"  period error (mean): {human_time(jitter)}")

    print(f"\nDone in {elapsed:.2f}s.")
    print("Tip: For reliable operation, choose a period comfortably above the p95 read latency (e.g., 2× p95).")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
