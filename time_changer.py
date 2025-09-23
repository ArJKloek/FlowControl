import csv
import time
from datetime import datetime

def respace_csv(file_path):
    with open(file_path, "r", newline="") as f:
        reader = list(csv.reader(f))
    header = reader[0]
    rows = reader[1:]
    if not rows:
        return

    # Start from the first timestamp
    start_ts = float(rows[0][0])
    for i, row in enumerate(rows):
        new_ts = start_ts + i * 3600
        row[0] = f"{new_ts:.3f}"
        row[1] = datetime.fromtimestamp(new_ts).strftime("%Y-%m-%d %H:%M:%S")

    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

# Run for each file
for fname in [
    "Data/log_CH4_20250923_123710.csv",
    "Data/log_CO2_20250923_123710.csv",
    "Data/log_H2_20250923_123710.csv"
]:
    respace_csv(fname)