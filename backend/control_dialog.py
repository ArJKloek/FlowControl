from PyQt5.QtWidgets import QDialog, QLayout
from PyQt5.QtCore import Qt
from PyQt5 import uic, QtCore
from PyQt5.QtGui import QPixmap
from resources_rc import *  # Import the compiled resources

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

        icon_path = ":/icon/massflow.png" if str(node.model).startswith("F") else ":/icon/massstream.png"
        pixmap = QPixmap(icon_path).scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lb_icon.setPixmap(pixmap)
       
        self._node = node

        # Subscribe to manager-level polling and register this node
        self.manager.measured.connect(self._on_poller_measured, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        self.manager.register_node_for_polling(self._node.port, self._node.address, period=1.0)

        # (optional) surface poller errors to the user
        self.manager.pollerError.connect(lambda m: self.le_status.setText(f"Port error: {m}"))
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
        self.ds_measure_flow.setMaximum(float(cap) if cap is not None else 1000)
        self.ds_setpoint_flow.setMaximum(float(cap) if cap is not None else 1000)
        
        self.lb_unit1.setText(str(node.unit))  # Assuming 'unit' attribute exists
        self.lb_unit2.setText(str(node.unit))  # Assuming 'unit' attribute exists
        self.le_model.setText(str(node.model))
        self.ds_setpoint_flow.setValue(float(node.fsetpoint) if node.fsetpoint is not None else 0.0)
        self._populate_fluids(node)  # <-- add this
        # --- Setpoint wiring ---
        self._sp_guard = False                      # prevents feedback loops
        self._pending_flow = None                   # last requested flow setpoint
        self._sp_timer = QtCore.QTimer(self)        # debounce so we don't spam the bus
        self._sp_timer.setSingleShot(True)
        self._sp_timer.setInterval(150)             # ms
        self._sp_timer.timeout.connect(self._send_setpoint_flow)

        self._sp_guard = False                      # prevents feedback loops
        self._pending_pct = None                   # last requested flow setpoint
        self._sp_pct_timer = QtCore.QTimer(self)        # debounce so we don't spam the bus
        self._sp_pct_timer.setSingleShot(True)
        self._sp_pct_timer.setInterval(150)             # ms
        self._sp_pct_timer.timeout.connect(self._send_setpoint_pct)




        # spinboxes & slider in sync
        self.ds_setpoint_flow.editingFinished.connect(self._on_sp_flow_changed)
        self.ds_setpoint_percent.editingFinished.connect(self._on_sp_percent_changed)
        self.vs_setpoint.sliderReleased.connect(self._on_sp_slider_changed)
        
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
            self.ds_setpoint_flow.setRange(0, int(round(cap)))
        else:
            # fallback range if capacity unknown
            self.ds_setpoint_flow.setRange(0, 1000)

        # Percent & slider: always 0..100
        self.ds_setpoint_percent.setRange(0, 100)
        self.vs_setpoint.setRange(0, 100)

    def _on_sp_slider_changed(self, val=None):
        if val is None:
            val = self.vs_setpoint.value()
        val = (val/100)*32000  # convert pct to raw
        self._pending_pct = float(val)
        print("pct change slider:", self._pending_pct)
        if self._combo_active:
            # defer until combo is deselected
            self._sp_pct_timer.stop()
        else:
            self._sp_pct_timer.start()
    
    def _on_sp_flow_changed(self, flow_val=None):
        if flow_val is None: 
            flow_val = self.ds_setpoint_flow.value()
        
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
        for w in (self.ds_setpoint_flow, self.ds_setpoint_percent, self.vs_setpoint):
            w.setEnabled(enabled)
        # If you actually have a *setpoint combobox*, disable it too (optional):
        if hasattr(self, "cb_setpoint"):
            self.cb_setpoint.setEnabled(enabled)

        # If we’re disabling, cancel any pending write
        if not enabled and hasattr(self, "_sp_timer"):
            self._sp_timer.stop()



    def _on_sp_percent_changed(self, pct_val=None):
        if pct_val is None:
            pct_val = self.ds_setpoint_percent.value()

        # queue the write (debounced)
        self._pending_pct = float(pct_val)
        print("pct change input:", self._pending_pct)
        if self._combo_active:
            self._sp_pct_timer.stop()
        else:
            self._sp_pct_timer.start()

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
            self.le_status.setText(f"Setpoint error: {e}")

    def _send_setpoint_pct(self):
        """Actually send the setpoint via the manager/poller (serialized with polling)."""
        # Don’t send for DMFM (meter)
        if getattr(self, "_is_meter", False):
            return
        try:
            if self._pending_pct is None:
                return
            self.manager.request_setpoint_pct(
                self._node.port,
                self._node.address,
                float(self._pending_pct)
            )
        except Exception as e:
            self.le_status.setText(f"Setpoint error: {e}")

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

        measure = d.get("measure")
        setpoint = d.get("setpoint")
        fsetpoint = d.get("fsetpoint")
        print("fSetpoint:", fsetpoint)
        # Calculate percentages
        measure_pct = (float(measure) / 32000 * 100) if measure is not None else None
        setpoint_pct = (float(setpoint) / 32000 * 100) if setpoint is not None else None

        # Display in spinboxes or labels
        if measure_pct is not None and hasattr(self, "ds_measure_percent"):
            self.ds_measure_percent.setValue(measure_pct)
        if setpoint_pct is not None and hasattr(self, "ds_setpoint_percent"):
            self.ds_setpoint_percent.setValue(setpoint_pct)
        
        if fsetpoint is not None and hasattr(self, "ds_setpoint_flow"):
            self.ds_setpoint_flow.setValue(float(fsetpoint))
    
        if measure_pct is not None and hasattr(self, "vs_measure"):
            self.vs_measure.setValue(float(measure_pct))

        if setpoint_pct is not None and hasattr(self, "vs_setpoint"):
            self.vs_setpoint.setValue(float(setpoint_pct))

        if f is not None:
            #self.le_measure_flow.setText("{:.3f}".format(float(f)))
            self.ds_measure_flow.setValue(float(f))
        nm = d.get("name")
        if nm:
            self.le_fluid.setText(str(nm))
        
        if payload is None:
            self.ds_measure_flow.setValue(0.0)
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
        self.le_status.setText(f"Fluid change failed: {msg}")
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


