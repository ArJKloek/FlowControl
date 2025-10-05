import os, time
os.environ.setdefault("FLOWCONTROL_USE_DUMMY", "1")
from backend.manager import ProparManager
from backend.poller import FMEASURE_DDE

# Simple non-Qt verification of dummy instrument logic
# NOTE: The main application uses QThreads; here we just instantiate and directly call instrument.

def main():
    m = ProparManager()
    # manually inject dummy nodes like scanner would
    # (Alternatively you could instantiate ProparScanner but that is QThread-based)
    
    # Test dummy_CO2
    node_info_co2 = type("_N", (), {})()
    node_info_co2.port = "dummy_CO2"; node_info_co2.address = 1
    inst_co2 = m.instrument("dummy_CO2", 1)
    print("CO2 ID:", getattr(inst_co2, "id", None))
    print("CO2 Initial fMeasure:", inst_co2.readParameter(FMEASURE_DDE))
    
    # Test dummy_H2
    node_info_h2 = type("_N", (), {})()
    node_info_h2.port = "dummy_H2"; node_info_h2.address = 1
    inst_h2 = m.instrument("dummy_H2", 1)
    print("H2 ID:", getattr(inst_h2, "id", None))
    print("H2 Initial fMeasure:", inst_h2.readParameter(FMEASURE_DDE))
    
    # Change setpoints for both
    inst_co2.writeParameter(206, 25.0)
    inst_h2.writeParameter(206, 50.0)
    time.sleep(0.2)
    print("CO2 New fSetpoint:", inst_co2.readParameter(206))
    print("H2 New fSetpoint:", inst_h2.readParameter(206))
    
    # Sample measurements from both
    for i in range(3):
        print(f"Sample {i+1}:")
        print("  CO2 fMeasure:", inst_co2.readParameter(FMEASURE_DDE))
        print("  H2 fMeasure:", inst_h2.readParameter(FMEASURE_DDE))
        time.sleep(0.3)

if __name__ == "__main__":
    main()
