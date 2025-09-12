from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextEdit, QTableView, QLayout, QMessageBox
from PyQt5.QtCore import Qt, QThread
from PyQt5 import uic, QtCore
from backend.models import NodesTableModel
from backend.worker import MeasureWorker
from backend.worker import FluidApplyWorker

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
        self.layout().setSizeConstraint(QLayout.SetFixedSize)  # dialog follows sizeHint
        self.advancedFrame.setVisible(False)
        self.btnAdvanced.setCheckable(True)
        self.btnAdvanced.toggled.connect(self._toggle_advanced)
        self.cb_fluids.currentIndexChanged.connect(self._on_fluid_selected)
        
       

        node = nodes[0] if isinstance(nodes, list) else nodes

        self._node = node
     
        self._start_measurement(node, manager)

        # Show instrument number if available
        if hasattr(node, "number"):
            self.le_number.setText(str(node.number))  # <-- add a QLineEdit named le_number in your .ui
        else:
            self.le_number.setText("N/A")

        # Set serial number
        self.le_serial.setText(str(node.serial))
        
        # Read and set usertag
        self.le_type.setText(str(node.dev_type))
        self._update_ui(node)



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
    def _start_measurement(self, node, manager):
        self._meas_thread = QThread(self)
        self._meas_worker = MeasureWorker(manager, node, interval=0.3)
        self._meas_worker.moveToThread(self._meas_thread)
        self._meas_thread.started.connect(self._meas_worker.run)
        #self._meas_worker.measured.connect(self._on_measured)
        self._meas_worker.measured.connect(self._on_measured, type=QtCore.Qt.QueuedConnection)
        self._meas_worker.finished.connect(self._meas_thread.quit)
        self._meas_worker.finished.connect(self._meas_worker.deleteLater)
        self._meas_thread.finished.connect(self._meas_thread.deleteLater)
        self._meas_thread.start()
    
    
    def _update_ui(self, node):
        self.le_usertag.setText(str(node.usertag))
        self.le_fluid.setText(str(node.fluid))
        self.le_capacity.setText(str(node.capacity))  # Placeholder for capacity if needed
        self.lb_unit1.setText(str(node.unit))  # Assuming 'unit' attribute exists
        self.lb_unit2.setText(str(node.unit))  # Assuming 'unit' attribute exists
        self._populate_fluids(node)  # <-- add this

    #def _on_measured(self, v):
    #    self.le_measure_flow.setText("—" if v is None else "{:.3f}".format(float(v)))
    @QtCore.pyqtSlot(object)
    def _on_measured(self, payload):
        print("Received payload:", payload)
        # payload can be dict, float, or None (for backward-compat)
        if isinstance(payload, dict):
            if "fmeasure" in payload and payload["fmeasure"] is not None:
                #print(payload["fmeasure"])
                self.le_measure_flow.setText("{:.3f}".format(float(payload["fmeasure"])))
            if "name" in payload and payload["name"]:
                self.le_fluid.setText(str(payload["name"]).strip())
            return

        if payload is None:
            self.le_measure_flow.setText("—")
            return
        ## numeric fallback (old behavior)
        #self.le_measure_flow.setText("{:.3f}".format(float(payload)))

    def closeEvent(self, e):
        if getattr(self, "_meas_worker", None):
            self._meas_worker.stop()
        super().closeEvent(e)

    def _toggle_advanced(self, checked):
        self.advancedFrame.setVisible(checked)
        self.adjustSize()  # grow/shrink the window to fit

    def _populate_fluids(self, node):
        """Fill cb_fluids from node.fluids_table (list of dicts with keys like: index, name, unit, etc.)."""
        self.cb_fluids.blockSignals(True)
        self.cb_fluids.clear()

        rows = getattr(node, "fluids_table", []) or []
        for r in rows:
            label = f"{r.get('index')} – {r.get('name')}"
            self.cb_fluids.addItem(label, r)  # store the whole row as userData

        # Select current fluid (prefer index if present, else by name)
        current_idx = getattr(node, "fluid_index", None)
        if current_idx is not None:
            for i in range(self.cb_fluids.count()):
                data = self.cb_fluids.itemData(i)
                if isinstance(data, dict) and int(data.get("index", -1)) == int(current_idx):
                    self.cb_fluids.setCurrentIndex(i)
                    break
        else:
            current_name = str(getattr(node, "fluid", ""))
            for i in range(self.cb_fluids.count()):
                data = self.cb_fluids.itemData(i)
                if isinstance(data, dict) and str(data.get("name", "")) == current_name:
                    self.cb_fluids.setCurrentIndex(i)
                    break

        self.cb_fluids.blockSignals(False)
    
    def _on_fluid_selected(self, idx):
        data = self.cb_fluids.itemData(idx)
        if not isinstance(data, dict) or "index" not in data:
            return
        self.cb_fluids.setEnabled(False)
        # optional: show a small status label if you have one, e.g. self.lb_status.setText("Applying…")

        self._fluid_thread = QThread(self)
        self._fluid_worker = FluidApplyWorker(self.manager, self._node, data["index"])
        self._fluid_worker.moveToThread(self._fluid_thread)
        self._fluid_thread.started.connect(self._fluid_worker.run)
        self._fluid_worker.done.connect(self._on_fluid_applied)
        self._fluid_worker.error.connect(self._on_fluid_error)
        self._fluid_worker.done.connect(self._fluid_thread.quit)
        self._fluid_worker.error.connect(self._fluid_thread.quit)
        self._fluid_worker.done.connect(self._fluid_worker.deleteLater)
        self._fluid_thread.finished.connect(self._fluid_thread.deleteLater)
        self._fluid_thread.start()

    def _on_fluid_applied(self, info: dict):
        # Update your node model
        self._node.fluid_index = info.get("index")
        self._node.fluid       = info.get("name")
        self._node.unit        = info.get("unit")
        cap = info.get("capacity")
        self._node.capacity    = int(cap) if cap is not None else None

        # Reflect in the UI
        self.le_fluid.setText(str(self._node.fluid))
        self.lb_unit1.setText(str(self._node.unit))
        self.lb_unit2.setText(str(self._node.unit))
        self.le_capacity.setText("" if self._node.capacity is None else str(self._node.capacity))

        self.cb_fluids.setEnabled(True)
        # optional: self.lb_status.setText("")

    def _on_fluid_error(self, msg: str):
        QMessageBox.warning(self, "Fluid change failed", msg)
        # revert combo to the node’s current index
        self._restore_combo_to_node()
        self.cb_fluids.setEnabled(True)

    def _restore_combo_to_node(self):
        idx = getattr(self._node, "fluid_index", None)
        if idx is None:
            return
        for i in range(self.cb_fluids.count()):
            data = self.cb_fluids.itemData(i)
            if isinstance(data, dict) and int(data.get("index", -1)) == int(idx):
                self.cb_fluids.blockSignals(True)
                self.cb_fluids.setCurrentIndex(i)
                self.cb_fluids.blockSignals(False)
                break
