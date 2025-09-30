import os, time
os.environ.setdefault("FLOWCONTROL_USE_DUMMY", "1")
from backend.manager import ProparManager
from backend.poller import FMEASURE_DDE

# Simple non-Qt verification of dummy instrument logic
# NOTE: The main application uses QThreads; here we just instantiate and directly call instrument.

def main():
    m = ProparManager()
    # manually inject dummy node like scanner would
    # (Alternatively you could instantiate ProparScanner but that is QThread-based)
    node_info = type("_N", (), {})()
    node_info.port = "DUMMY0"; node_info.address = 1
    # Acquire dummy instrument and exercise API
    inst = m.instrument("DUMMY0", 1)
    print("ID:", getattr(inst, "id", None))
    print("Initial fMeasure:", inst.readParameter(FMEASURE_DDE))
    # change setpoint
    inst.writeParameter(206, 25.0)
    time.sleep(0.2)
    print("New fSetpoint:", inst.readParameter(206))
    for _ in range(3):
        print("fMeasure sample:", inst.readParameter(FMEASURE_DDE))
        time.sleep(0.3)

if __name__ == "__main__":
    main()
