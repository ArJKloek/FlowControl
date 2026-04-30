import propar
import time
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

# Port selection priority:
# 1) first CLI argument
# 2) PROPAR_PORT environment variable
# 3) Raspberry Pi default
port = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PROPAR_PORT", "/dev/ttyUSB0")

dut = propar.instrument(port)

print()
print("Testing using propar @", propar.__file__)
print("Using port:", port)
print()

n = 10

all_parameters = dut.db.get_all_parameters()
bt = time.perf_counter()
for i in range(n):
  for p in all_parameters:
    dut.read_parameters([p])  
et = time.perf_counter()

print("{:<20}{:>8}".format("read all parameters", (et - bt)                       / n))
print("{:<20}{:>8}".format("read one parameter ", (et - bt) / len(all_parameters) / n))


def _read_parameter_row(instrument, p):
  req = dict(p)
  row = {
    "parameter": req.get("dde_nr", ""),
    "parameter_requested": req.get("dde_nr", ""),
    "parameter_read": "",
    "dde_nr": req.get("dde_nr", ""),
    "name": req.get("parm_name", ""),
    "longname": "",
    "description": "",
    "vartype": req.get("parm_type", ""),
    "readable": "",
    "writable": "",
    "status": "",
    "value": "",
    "error": "",
  }

  try:
    res = instrument.read_parameters([req])
  except Exception as exc:
    row["error"] = str(exc)
    return row

  # propar typically returns a list with one dict.
  if isinstance(res, (list, tuple)) and len(res) > 0 and isinstance(res[0], dict):
    item = res[0]
    row["parameter_read"] = item.get("parameter", row["parameter_requested"])
    row["status"] = item.get("status", "")
    row["value"] = item.get("data", "")
    if item.get("status", 1) != 0:
      row["error"] = item.get("message", "read failed")
    return row

  # Fallback for unexpected return shapes.
  row["value"] = res
  return row


def export_parameter_snapshot(instrument, params, output_path):
  fieldnames = [
    "parameter",
    "parameter_requested",
    "parameter_read",
    "dde_nr",
    "name",
    "longname",
    "description",
    "vartype",
    "readable",
    "writable",
    "status",
    "value",
    "error",
  ]
  ok_count = 0
  fail_count = 0

  with output_path.open("w", newline="", encoding="utf-8-sig") as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    writer.writeheader()
    for p in params:
      row = _read_parameter_row(instrument, p)
      writer.writerow(row)
      if str(row.get("status")) == "0":
        ok_count += 1
      elif row.get("error"):
        fail_count += 1

  return ok_count, fail_count


script_dir = Path(__file__).resolve().parent
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
safe_port = "".join(c if c.isalnum() else "_" for c in str(port))
out_csv = script_dir / f"instrument_parameters_{safe_port}_{stamp}.csv"

ok_count, fail_count = export_parameter_snapshot(dut, all_parameters, out_csv)
print(f"Snapshot saved: {out_csv}")
print(f"Read OK: {ok_count}  Read failures: {fail_count}")