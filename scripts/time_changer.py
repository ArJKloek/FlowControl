import csv
from datetime import datetime

def adjust_csv(file_path):
    with open(file_path, "r", newline="") as f:
        reader = list(csv.reader(f))
    header = reader[0]
    rows = reader[1:]

    # Find indices for columns
    kind_idx = header.index("kind")
    name_idx = header.index("name")
    ts_idx = header.index("ts")
    iso_idx = header.index("iso")

    # Start from the first timestamp
    start_ts = float(rows[0][ts_idx])
    current_ts = start_ts

    for i, row in enumerate(rows):
        if row[kind_idx] == "measure" and row[name_idx] == "fMeasure":
            row[ts_idx] = f"{current_ts:.3f}"
            row[iso_idx] = datetime.fromtimestamp(current_ts).strftime("%Y-%m-%d %H:%M:%S")
            last_fmeasure_ts = current_ts
            last_fmeasure_iso = row[iso_idx]
            current_ts += 3600  # increment by 1 hour
        elif row[kind_idx] == "setpoint" and row[name_idx] == "fSetpoint":
            # Use previous fMeasure timestamp
            row[ts_idx] = f"{last_fmeasure_ts:.3f}"
            row[iso_idx] = last_fmeasure_iso

    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

# Example usage:
for fname in [
    "Data/log_CH4_20250923_123710.csv",
    "Data/log_CO2_20250923_123710.csv",
    "Data/log_H2_20250923_123710.csv"
]:
    adjust_csv(fname)