import propar
import time
import random 
import os
import sys

# Port selection priority:
# 1) first CLI argument
# 2) PROPAR_PORT environment variable
# 3) Raspberry Pi default
port = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PROPAR_PORT", "/dev/ttyUSB1")

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