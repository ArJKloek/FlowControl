from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextEdit, QTableView
from PyQt5 import uic
from backend.models import NodesTableModel

class NodeViewer(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        uic.loadUi("ui/nodeviewer.ui", self)
    
        self.model = NodesTableModel(self.manager)
        self.table.setModel(self.model)

        self.btnScan.clicked.connect(self.onScan)
        self.manager.scanProgress.connect(lambda p: self.log.append(f"Scanning {p}..."))
        self.manager.scanError.connect(lambda p, e: self.log.append(f"[{p}] {e}"))
        self.manager.scanFinished.connect(lambda: self.log.append("Scan finished."))

        self.table.doubleClicked.connect(self.onOpenInstrument)    
        self.btnConnect.clicked.connect(self.onConnect)

    def onScan(self):
        self.manager.scan()

    def onConnect(self):
        # Iterate over all found nodes in the model
        for node in self.model._nodes:
            dlg = FlowChannelDialog(self.manager, [node], self)
            dlg.show()  # Use .exec_() for modal, .show() for non-modal

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

    def openInstrumentByNumber(self, number):
        # Assuming you have access to the instrument_list from your scanner
        try:
            instrument_info = self.manager.scanner.instrument_list[number]["info"]
            inst = self.manager.instrument(instrument_info.port, instrument_info.address)
            device_id = inst.id
            measure = inst.measure
            self.log.append(f"Instrument #{number}: ID: {device_id}, Measure: {measure}")
        except Exception as e:
            self.log.append(f"Instrument error: {e}")

class FlowChannelDialog(QDialog):
    def __init__(self, manager, nodes, parent=None):
        super().__init__(parent)
        self.manager = manager
        uic.loadUi("ui/flowchannel.ui", self)
        
        node = nodes[0] if isinstance(nodes, list) else nodes

        # Set serial number
        self.le_serial.setText(str(node.serial))
        
        # Read and set usertag
        self.le_type.setText(str(node.type))
       
        try:
            inst = self.manager.instrument(node.port, node.address)
            usertag = inst.readParameter(115)
            self.le_usertag.setText(str(usertag))
        except Exception as e:
            self.le_usertag.setText(f"Error: {e}")