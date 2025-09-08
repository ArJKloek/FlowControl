# propar_qt/main.py
import sys
from PyQt5.QtWidgets import (
QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit, QTableView
)

from . import ProparManager
from .models import NodesTableModel

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Propar Node Browser")


        self.manager = ProparManager()
        self.model = NodesTableModel(self.manager)


        self.table = QTableView()
        self.table.setModel(self.model)


        self.log = QTextEdit(readOnly=True)
        self.btnScan = QPushButton("Scan")


        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(self.btnScan)
        layout.addWidget(self.log)


        self.btnScan.clicked.connect(self.onScan)
        self.manager.scanProgress.connect(lambda p: self.log.append(f"Scanning {p}..."))
        self.manager.scanError.connect(lambda p, e: self.log.append(f"[{p}] {e}"))
        self.manager.scanFinished.connect(lambda: self.log.append("Scan finished."))


        self.table.doubleClicked.connect(self.onOpenInstrument)


    def onScan(self):
        self.manager.scan()


    def onOpenInstrument(self, index):
        # Read a couple of parameters as a proof of life
        node = self.model._nodes[index.row()]
        try:
            inst = self.manager.instrument(node.port, node.address)
            device_id = inst.id # DDE #1 (string)
            measure = inst.measure # DDE #8 (0..32000)
            self.log.append(f"Node {node.address} ID: {device_id}, Measure: {measure}")
        except Exception as e:
            self.log.append(f"Instrument error: {e}")

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(900, 520)
    w.show()
    sys.exit(app.exec_())




if __name__ == "__main__":
    main()