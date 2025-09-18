from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextEdit, QTableView, QLayout, QMessageBox, QWIDGETSIZE_MAX
from PyQt5.QtCore import Qt, QThread
from PyQt5 import uic, QtCore
from backend.models import NodesTableModel
from PyQt5.QtGui import QIcon
from resources_rc import *  # Import the compiled resources

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
    
        self.model = NodesTableModel(self.manager)
        self.table.setModel(self.model)

        self.btnScan.clicked.connect(self.onScan)
        self.manager.scanProgress.connect(lambda p: self.log.append(f"Scanning {p}..."))
        self.manager.scanError.connect(lambda p, e: self.log.append(f"[{p}] {e}"))
        self.manager.scanFinished.connect(lambda: self.log.append("Scan finished."))
        self.manager.scanFinished.connect(self.refresh_table)  # <-- update table after scan

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
            dlg.show()  # Use .exec_() for modal, .show() for non-modal
    
    def onOpenInstrument(self, index):
        # Read a couple of parameters as a proof of life
        node = self.model._nodes[index.row()]
        dlg = open_flow_dialog(self.manager, node, self)
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

class ControllerDialog(QDialog):
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
        self._last_ts = None
        self._combo_active = False
        self.cb_fluids.installEventFilter(self)   # gate setpoint while this combo is active


        node = nodes[0] if isinstance(nodes, list) else nodes

        self._node = node
        # Subscribe to manager-level polling and register this node
        self.manager.measured.connect(self._on_poller_measured, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        self.manager.register_node_for_polling(self._node.port, self._node.address, period=1.0)

        # (optional) surface poller errors to the user
        self.manager.pollerError.connect(lambda m: QMessageBox.warning(self, "Port error", m))

        #self._start_measurement(node, manager)

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
        self._update_setpoint_enabled_state()

    def eventFilter(self, obj, ev):
        if obj is self.cb_fluids:
            if ev.type() == QtCore.QEvent.FocusIn:
                self._combo_active = True
                # pause any pending send while user is in the combo
                self._sp_timer.stop()
            elif ev.type() == QtCore.QEvent.FocusOut:
                self._combo_active = False
                # user finished with the combo → send the last pending setpoint (if any)
                if getattr(self, "_pending_flow", None) is not None:
                    self._send_setpoint_flow()
        return super().eventFilter(obj, ev)

    def _update_ui(self, node):
        self.le_usertag.setText(str(node.usertag))
        self.le_fluid.setText(str(node.fluid))

        # one-decimal capacity
        cap = getattr(node, "capacity", None)
        self.le_capacity.setText("" if cap is None else f"{float(cap):.1f}")

        self.lb_unit1.setText(str(node.unit))  # Assuming 'unit' attribute exists
        self.lb_unit2.setText(str(node.unit))  # Assuming 'unit' attribute exists
        self.le_model.setText(str(node.model))
        self.sb_setpoint_flow.setValue(int(node.fsetpoint) if node.fsetpoint is not None else 0)
        self._populate_fluids(node)  # <-- add this
        # --- Setpoint wiring ---
        self._sp_guard = False                      # prevents feedback loops
        self._pending_flow = None                   # last requested flow setpoint
        self._sp_timer = QtCore.QTimer(self)        # debounce so we don't spam the bus
        self._sp_timer.setSingleShot(True)
        self._sp_timer.setInterval(150)             # ms
        self._sp_timer.timeout.connect(self._send_setpoint_flow)

        # spinboxes & slider in sync
        self.sb_setpoint_flow.editingFinished.connect(self._on_sp_flow_changed)
        self.sb_setpoint_percent.editingFinished.connect(self._on_sp_percent_changed)
        self.vs_setpoint.sliderReleased.connect(self.sb_setpoint_percent.setValue)
        
        # and stop sending on every incremental change:
        #self.sb_setpoint_flow.valueChanged.disconnect(self._on_sp_flow_changed)
        #self.sb_setpoint_percent.valueChanged.disconnect(self._on_sp_percent_changed)
        # initialize ranges from capacity, if available
        self._apply_capacity_limits()
     
    def _apply_capacity_limits(self):
        """Set sensible ranges for flow/% based on capacity shown in the UI."""
        try:
            cap_txt = (self.le_capacity.text() or "").strip()
            cap = float(cap_txt) if cap_txt else 0.0
        except Exception:
            cap = 0.0

        # Flow setpoint: 0..capacity (int granularity here; change to decimals if your widget allows)
        if cap > 0:
            self.sb_setpoint_flow.setRange(0, int(round(cap)))
        else:
            # fallback range if capacity unknown
            self.sb_setpoint_flow.setRange(0, 1000)

        # Percent & slider: always 0..100
        self.sb_setpoint_percent.setRange(0, 100)
        self.vs_setpoint.setRange(0, 100)

    def _on_sp_flow_changed(self, flow_val=None):
        if flow_val is None: 
            flow_val = self.sb_setpoint_flow.value()
        
        if self._sp_guard:
            return

        # keep % + slider in sync
        try:
            cap_txt = (self.le_capacity.text() or "").strip()
            cap = float(cap_txt) if cap_txt else 0.0
        except Exception:
            cap = 0.0

        if cap > 0:
            pct = max(0, min(100, int(round((float(flow_val) / cap) * 100))))
            self._sp_guard = True
            try:
                self.sb_setpoint_percent.setValue(pct)
                self.vs_setpoint.setValue(pct)
            finally:
                self._sp_guard = False

        # queue the write (debounced)
        self._pending_flow = float(flow_val)
        if self._combo_active:
            # defer until combo is deselected
            self._sp_timer.stop()
        else:
            self._sp_timer.start()
    
    def _update_setpoint_enabled_state(self):
        # Decide from node.dev_type or the UI field (case-insensitive)
        t = (str(getattr(self._node, "dev_type", "")) or self.le_type.text() or "").strip().upper()
        self._is_meter = (t == "DMFM")  # adjust if you have variants like "DMFM-xxx"

        enabled = not self._is_meter
        # Disable the setpoint widgets (flow, %, slider)
        for w in (self.sb_setpoint_flow, self.sb_setpoint_percent, self.vs_setpoint):
            w.setEnabled(enabled)
        # If you actually have a *setpoint combobox*, disable it too (optional):
        if hasattr(self, "cb_setpoint"):
            self.cb_setpoint.setEnabled(enabled)

        # If we’re disabling, cancel any pending write
        if not enabled and hasattr(self, "_sp_timer"):
            self._sp_timer.stop()



    def _on_sp_percent_changed(self, pct_val=None):
        if pct_val is None:
            pct_val = self.sb_setpoint_percent.value()
        
        if self._sp_guard:
            return

        # convert % -> flow using capacity
        try:
            cap_txt = (self.le_capacity.text() or "").strip()
            cap = float(cap_txt) if cap_txt else 0.0
        except Exception:
            cap = 0.0

        flow = float(pct_val) * cap / 100.0 if cap > 0 else float(pct_val)  # fallback: treat % as flow if cap unknown

        self._sp_guard = True
        try:
            self.sb_setpoint_flow.setValue(int(round(flow)))
            self.vs_setpoint.setValue(int(pct_val))
        finally:
            self._sp_guard = False

        # queue the write (debounced)
        self._pending_flow = float(flow)
        if self._combo_active:
            self._sp_timer.stop()
        else:
            self._sp_timer.start()

    def _send_setpoint_flow(self):
        """Actually send the setpoint via the manager/poller (serialized with polling)."""
        # Don’t send for DMFM (meter)
        if getattr(self, "_is_meter", False):
            return
        try:
            if self._pending_flow is None:
                return
            self.manager.request_setpoint_flow(
                self._node.port,
                self._node.address,
                float(self._pending_flow)
            )
        except Exception as e:
            QMessageBox.warning(self, "Setpoint", f"Failed to send setpoint: {e}")

    
    @QtCore.pyqtSlot(object)
    def _on_poller_measured(self, payload):
        #print("Received payload:", payload)
        # payload can be dict, float, or None (for backward-compat)
        if payload.get("port") != self._node.port or payload.get("address") != self._node.address:
            return
        ts = payload.get("ts")
        if ts is not None and ts == self._last_ts:
            return  # drop duplicate
        self._last_ts = ts

        d = payload.get("data") or {}
        f = d.get("fmeasure")
        if f is not None:
            self.le_measure_flow.setText("{:.3f}".format(float(f)))
        nm = d.get("name")
        if nm:
            self.le_fluid.setText(str(nm))
        
        if payload is None:
            self.le_measure_flow.setText("—")
            return
        ## numeric fallback (old behavior)
        #self.le_measure_flow.setText("{:.3f}".format(float(payload)))

    def closeEvent(self, e):
        try:
            self.manager.unregister_node_from_polling(self._node.port, self._node.address)
            self.manager.measured.disconnect(self._on_poller_measured)
        except Exception:
            pass
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
        try:
            self.manager.request_fluid_change(self._node.port, self._node.address, data["index"])
        finally:
            # Re-enable immediately; UI will reflect new name via poller measurement
            self.cb_fluids.setEnabled(True)


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
        
        cap = info.get("capacity")
        self._node.capacity = None if cap is None else float(cap)   # keep as float, not int
        
        self.le_capacity.setText("" if self._node.capacity is None else f"{self._node.capacity:.1f}")

        self.cb_fluids.setEnabled(True)
        # optional: self.lb_status.setText("")
        self._apply_capacity_limits()  # in case capacity changed
        self._update_setpoint_enabled_state()

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


class MeterDialog(QDialog):
    def __init__(self, manager, nodes, parent=None):
        super().__init__(parent)
        self.manager = manager
        uic.loadUi("ui/flowchannel_meter.ui", self)
        self.setWindowIcon(QIcon(":/icon/massview.png"))

        # in your dialog __init__ after loadUi(...)
        # after uic.loadUi(...) and initial visibility changes
        #self.adjustSize()                         # let Qt compute the right size first
        #h = self.height()                         # or: self.sizeHint().height()
        #self.setMinimumHeight(h)
        #self.setMaximumHeight(h)                  # height fixed
        # leave width free (user can resize horizontally)

        #self.layout().setSizeConstraint(QLayout.SetFixedSize)  # dialog follows sizeHint

        self.advancedFrame.setVisible(False)
        self._last_flow = None

        self._unlock_height()
        self.adjustSize()
        self._lock_height_to_current()
        
        self.btnAdvanced.setCheckable(True)
        self.btnAdvanced.toggled.connect(self._toggle_advanced)
        self.cb_fluids.currentIndexChanged.connect(self._on_fluid_selected)
        self._last_ts = None
        self._combo_active = False
        self.cb_fluids.installEventFilter(self)   # gate setpoint while this combo is active


        node = nodes[0] if isinstance(nodes, list) else nodes

        self._node = node
        # Subscribe to manager-level polling and register this node
        self.manager.measured.connect(self._on_poller_measured, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        self.manager.register_node_for_polling(self._node.port, self._node.address, period=1.0)

        # (optional) surface poller errors to the user
        self.manager.pollerError.connect(lambda m: QMessageBox.warning(self, "Port error", m))
        
        self._sp_guard = False                      # prevents feedback loops
        self._pending_flow = None                   # last requested flow setpoint
        self._sp_timer = QtCore.QTimer(self)        # debounce so we don't spam the bus
        self._sp_timer.setSingleShot(True)
        self._sp_timer.setInterval(150)             # ms
        
        #self._start_measurement(node, manager)

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
        #self._update_setpoint_enabled_state()

    def eventFilter(self, obj, ev):
        if obj is self.cb_fluids:
            if ev.type() == QtCore.QEvent.FocusIn:
                self._combo_active = True
                # pause any pending send while user is in the combo
                self._sp_timer.stop()
            elif ev.type() == QtCore.QEvent.FocusOut:
                self._combo_active = False
                # user finished with the combo → send the last pending setpoint (if any)
                if getattr(self, "_pending_flow", None) is not None:
                    self._send_setpoint_flow()
        return super().eventFilter(obj, ev)

    def _unlock_height(self):
        self.setMinimumHeight(0)
        self.setMaximumHeight(QWIDGETSIZE_MAX)

    def _lock_height_to_current(self):
        h = self.height()  # or: self.sizeHint().height()
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)


    def _update_ui(self, node):
        self.le_usertag.setText(str(node.usertag))
        self.le_fluid.setText(str(node.fluid))

        # one-decimal capacity
        cap = getattr(node, "capacity", None)
        self.le_capacity.setText("" if cap is None else f"{float(cap):.1f}")

        self.lb_unit.setText(str(node.unit))  # Assuming 'unit' attribute exists
        self.le_model.setText(str(node.model))

        #self.sb_setpoint_flow.setValue(int(node.fsetpoint) if node.fsetpoint is not None else 0)
        
        self._populate_fluids(node)  # <-- add this
        # --- Setpoint wiring ---
        # and stop sending on every incremental change:
        #self.sb_setpoint_flow.valueChanged.disconnect(self._on_sp_flow_changed)
        #self.sb_setpoint_percent.valueChanged.disconnect(self._on_sp_percent_changed)
        # initialize ranges from capacity, if available
        self._apply_capacity_limits()
     
    def _apply_capacity_limits(self):
        """Set sensible ranges for flow/% based on capacity shown in the UI."""
        try:
            cap_txt = (self.le_capacity.text() or "").strip()
            cap = float(cap_txt) if cap_txt else 0.0
        except Exception:
            cap = 0.0

        # Flow setpoint: 0..capacity (int granularity here; change to decimals if your widget allows)
        #if cap > 0:
        #    self.sb_setpoint_flow.setRange(0, int(round(cap)))
        #else:
            # fallback range if capacity unknown
        #    self.sb_setpoint_flow.setRange(0, 1000)

        # Percent & slider: always 0..100
        #self.sb_setpoint_percent.setRange(0, 100)
        #self.vs_setpoint.setRange(0, 100)
    
    
    @QtCore.pyqtSlot(object)
    def _on_poller_measured(self, payload):
        #print("Received payload:", payload)
        # payload can be dict, float, or None (for backward-compat)
        if payload.get("port") != self._node.port or payload.get("address") != self._node.address:
            return
        ts = payload.get("ts")
        if ts is not None and ts == self._last_ts:
            return  # drop duplicate
        self._last_ts = ts

        d = payload.get("data") or {}
        f = d.get("fmeasure")
        if f is not None:
            self._last_flow = float(f)
            self.le_measure_flow.setText("{:.3f}".format(float(f)))
            self._update_flow_progress(self._last_flow)   # <<< update the bar

        nm = d.get("name")
        if nm:
            self.le_fluid.setText(str(nm))
        
        if payload is None:
            self.le_measure_flow.setText("—")
            return
        ## numeric fallback (old behavior)
        #self.le_measure_flow.setText("{:.3f}".format(float(payload)))

    def closeEvent(self, e):
        try:
            self.manager.unregister_node_from_polling(self._node.port, self._node.address)
            self.manager.measured.disconnect(self._on_poller_measured)
        except Exception:
            pass
        super().closeEvent(e)

    def _toggle_advanced(self, checked):
        self._unlock_height()                 # allow the window to grow/shrink
        self.advancedFrame.setVisible(checked)
        self.layout().invalidate()            # make sure layout recalculates
        self.layout().activate()
        self.adjustSize()                     # compute new natural size
        self._lock_height_to_current()        # fix height at the new size
        
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
    
    def _update_flow_progress(self, flow: float):
        # if this UI doesn't have a progress bar (controller UI), just skip
        pb = getattr(self, "pb_flow", None)
        if pb is None:
            return

        unit = (getattr(self, "lb_unit", None).text().strip()
                if getattr(self, "lb_unit", None) else "")
        # parse capacity
        try:
            cap = float((self.le_capacity.text() or "0").strip())
        except Exception:
            cap = 0.0

        # QProgressBar is int-based → use tenths to keep 0.1 precision
        scale = 10
        maxv = int(round(cap * scale)) if cap > 0 else 1000  # fallback
        pb.setRange(0, maxv)

        val = int(round(max(0.0, min(flow, cap if cap > 0 else flow)) * scale))
        pb.setValue(val)

        # Show the numeric value on the bar
        pb.setTextVisible(True)
        pb.setFormat(f"{flow:.1f} {unit}")  # one decimal


    def _on_fluid_selected(self, idx):
        data = self.cb_fluids.itemData(idx)
        if not isinstance(data, dict) or "index" not in data:
            return
        self.cb_fluids.setEnabled(False)
        try:
            self.manager.request_fluid_change(self._node.port, self._node.address, data["index"])
        finally:
            # Re-enable immediately; UI will reflect new name via poller measurement
            self.cb_fluids.setEnabled(True)


    def _on_fluid_applied(self, info: dict):
        # Update your node model
        self._node.fluid_index = info.get("index")
        self._node.fluid       = info.get("name")
        self._node.unit        = info.get("unit")
        cap = info.get("capacity")
        self._node.capacity    = int(cap) if cap is not None else None

        # Reflect in the UI
        self.le_fluid.setText(str(self._node.fluid))
        self.lb_unit.setText(str(self._node.unit))
        
        cap = info.get("capacity")
        self._node.capacity = None if cap is None else float(cap)   # keep as float, not int
        
        self.le_capacity.setText("" if self._node.capacity is None else f"{self._node.capacity:.1f}")

        self.cb_fluids.setEnabled(True)
        # optional: self.lb_status.setText("")
        self._apply_capacity_limits()  # in case capacity changed

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
