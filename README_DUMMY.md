# Dummy Instrument Usage

A simulated Propar instrument is available for offline UI / logic testing.

## Enable

Two ways:

1. Set environment variable before launching:
   - Windows PowerShell:
     `$Env:FLOWCONTROL_USE_DUMMY = '1'; python main.py`
2. Pass the `--dummy` command-line flag:
   `python main.py --dummy`

## What You Get

- One virtual node appears with port `DUMMY0`, address `1`.
- Device type: `DMFC`, serial `SIM001`.
- Fluids table: AIR, N2, O2, CO2.
- fSetpoint starts at 10.0 (engineering units). fMeasure oscillates smoothly around setpoint with mild noise.
- You can change setpoint (flow or percentage), fluid index, and usertag; changes persist in the session.
- No physical serial port is opened; a stub master object is provided so the poller can adjust timeouts safely.

## Polling & Logging

The dummy node is treated like a normal node by the poller. Logging works; values will show slight variation.

## Multiple Dummies?

Currently only one dummy (`DUMMY0`, address 1). Extend by copying the injection block in `backend/scanner.py` and adjusting address / number.

## Relevant Files

- `backend/dummy_instrument.py`: Implementation.
- `backend/scanner.py`: Injection logic when env var set.
- `backend/manager.py`: Returns `DummyInstrument` for `DUMMY*` ports when enabled.

## Removal

Unset the environment variable or omit the flag and restart; the dummy node disappears.

---
Happy testing!
