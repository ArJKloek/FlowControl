from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextEdit, QTableView
from PyQt5.QtCore import Qt, QThread
from PyQt5 import uic
from backend.models import NodesTableModel
from backend.worker import MeasureWorker

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
        # in your dialog __init__ after loadUi(...)
        self.advancedFrame.setVisible(False)
        self.btnAdvanced.setCheckable(True)
        self.btnAdvanced.toggled.connect(self._toggle_advanced)

       

        node = nodes[0] if isinstance(nodes, list) else nodes

        self._node = node
        self._meas_thread = QThread(self)
        self._meas_worker = MeasureWorker(self.manager, self._node, interval=1)
        self._meas_worker.moveToThread(self._meas_thread)
        self._meas_thread.started.connect(self._meas_worker.run)
        self._meas_worker.measured.connect(self._on_measured)
        self._meas_worker.finished.connect(self._meas_thread.quit)
        self._meas_worker.finished.connect(self._meas_worker.deleteLater)
        self._meas_thread.finished.connect(self._meas_thread.deleteLater)
        self._meas_thread.start()


        # Show instrument number if available
        if hasattr(node, "number"):
            self.le_number.setText(str(node.number))  # <-- add a QLineEdit named le_number in your .ui
        else:
            self.le_number.setText("N/A")

        # Set serial number
        self.le_serial.setText(str(node.serial))
        
        # Read and set usertag
        self.le_type.setText(str(node.dev_type))
        self.le_usertag.setText(str(node.usertag))
        self.le_fluid.setText(str(node.fluid))
        self.le_capacity.setText(str(node.capacity))  # Placeholder for capacity if needed
        self.lb_unit1.setText(str(node.unit))  # Assuming 'unit' attribute exists
        self.lb_unit2.setText(str(node.unit))  # Assuming 'unit' attribute exists


        #try:
        #    inst = self.manager.instrument(node.port, node.address)
        #    print(node.port, node.address)
        #    usertag = inst.readParameter(115)
        #    self.le_usertag.setText(str(usertag))
        #except Exception as e:
        #    self.le_usertag.setText(f"Error: {e}")
        
        #param_numbers = [1, 6, 21, 24, 115]  # Example parameter numbers
        #for p in param_numbers:
        #    try:
        #        value = inst.readParameter(p)
        #        print(f"Parameter {p}: {value}")
        #    except Exception as e:
        #        print(f"Error reading parameter {p}: {e}")
    
    def _on_measured(self, v):
        self.le_measure_flow.setText("—" if v is None else "{:.3f}".format(float(v)))

    def closeEvent(self, e):
        if getattr(self, "_meas_worker", None):
            self._meas_worker.stop()
        super().closeEvent(e)

    def _toggle_advanced(self, checked):
        self.advancedFrame.setVisible(checked)
        self.btnAdvanced.setText("Hide options" if checked else "Show options")
