# debug_signals.py
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtCore import Qt

def connect_once(signal, slot, *, qtype=Qt.QueuedConnection):
    try:
        signal.disconnect(slot)
    except (TypeError, RuntimeError):
        pass
    signal.connect(slot, type=qtype)

def tap_signal(signal, name=""):
    def _tap(*args):
        print(f"[TAP {name}] args={args}")
    signal.connect(_tap, type=Qt.QueuedConnection | Qt.UniqueConnection)
    return _tap

def attach_spy(signal):
    return QSignalSpy(signal)

def spy_count(spy):
    return len(spy)          # <-- PyQt5: use len()

def spy_last(spy):
    return spy[-1] if len(spy) else None
