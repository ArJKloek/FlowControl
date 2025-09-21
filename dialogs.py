from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextEdit, QTableView, QLayout, QMessageBox, QWIDGETSIZE_MAX
from PyQt5.QtCore import Qt, QThread
from PyQt5 import uic, QtCore
from backend.models import NodesTableModel
from PyQt5.QtGui import QIcon, QPixmap
from resources_rc import *  # Import the compiled resources
from backend.meter_dialog import MeterDialog
from backend.control_dialog import ControllerDialog 
from backend.window_tiler import DialogTiler  # add this import

def open_flow_dialog(manager, node, parent=None):
        dev_type = (str(getattr(node, "dev_type", "")) or "").strip().upper()
        if dev_type.startswith("DMFM"):
            return MeterDialog(manager, node, parent)
        return ControllerDialog(manager, node, parent)


class NodeViewer(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        uic.loadUi("ui/nodeviewer.ui", self)
    
        self.tiler = DialogTiler(margin=12, gap=12)   # NEW: one tiler for this window

        
        self.model = NodesTableModel(self.manager)
        self.table.setModel(self.model)

        self.btnScan.clicked.connect(self.onScan)
        self.manager.scanProgress.connect(lambda p: self.log.append(f"Scanning {p}..."))
        self.manager.scanError.connect(lambda p, e: self.log.append(f"[{p}] {e}"))
        self.manager.scanFinished.connect(lambda: self.log.append("Scan finished."))
        self.manager.scanFinished.connect(self.refresh_table)  # <-- update table after scan
        self.manager.scanFinished.connect(                                  # NEW
            lambda: self.manager.start_parallel_polling(default_period=0.2)
        )
        self.table.doubleClicked.connect(self.onOpenInstrument)    
        self.btnConnect.clicked.connect(self.onConnect)

    def onScan(self):
        self.model.clear()         # Remove previous nodes from the table
        self.manager.scan()

    def refresh_table(self):
        # This will notify the view to update its contents
        self.model.layoutChanged.emit()

    def onConnect(self):
        # Iterate over all found nodes in the model
        for node in self.model._nodes:
            dlg = open_flow_dialog(self.manager, node, self)
            self.tiler.place(dlg)    # place dialog using the tiler
            dlg.show()  # Use .exec_() for modal, .show() for non-modal
    
    def onOpenInstrument(self, index):
        # Read a couple of parameters as a proof of life
        node = self.model._nodes[index.row()]
        dlg = open_flow_dialog(self.manager, node, self)
        self.tiler.place(dlg)         # place dialog using the tiler
        dlg.show()

        # Start logging per instrument
        #mainwin = self.parent()
        #if hasattr(mainwin, "start_logging_for_node"):
        #    mainwin.start_logging_for_node(node)

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

