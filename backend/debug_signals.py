# debug_signals.py
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QSignalSpy

def connect_once(signal, slot, *, qtype=Qt.QueuedConnection):
    """Disconnect the pair (if any) and connect once."""
    try:
        signal.disconnect(slot)
    except (TypeError, RuntimeError):
        pass
    signal.connect(slot, type=qtype)

def tap_signal(signal, name=""):
    """Print every emission (use ONLY while debugging)."""
    def _tap(*args):
        print(f"[TAP {name}] args={args}")
    # UniqueConnection so we don’t double-tap
    signal.connect(_tap, type=Qt.QueuedConnection | Qt.UniqueConnection)
    return _tap  # keep a ref so it doesn’t get GC’d

def attach_spy(signal):
    """Attach a QSignalSpy to count/peek emissions."""
    return QSignalSpy(signal)

def spy_count(spy):
    """How many times the signal fired so far."""
    return spy.count()

def spy_last(spy):
    """Last emission args (list) or None if none."""
    return spy[-1] if spy.count() else None
