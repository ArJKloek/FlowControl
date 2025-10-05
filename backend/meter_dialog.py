from PyQt5.QtWidgets import QDialog, QWIDGETSIZE_MAX
from PyQt5.QtCore import Qt
from PyQt5 import uic, QtCore
from PyQt5.QtGui import  QPixmap
from resources_rc import *  # Import the compiled resources
from typing import Optional

class MeterDialog(QDialog):
    def __init__(self, manager, nodes, parent=None):
        super().__init__(parent)
        self.manager = manager
        uic.loadUi("ui/flowchannel_meter.ui", self)
        self._placed_once = False  
        self._init_status_timer()

        #self.setWindowIcon(QIcon("/icon/massview.png"))
        pixmap = QPixmap(":/icon/massview.png").scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lb_icon.setPixmap(pixmap)
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
        self.manager.pollerError.connect(lambda m: self._set_status(f"Port error: {m}", level="error", timeout_ms=10000))

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
        
        # Add test functionality for dummy instruments
        self._setup_dummy_testing()

    def _setup_dummy_testing(self):
        """Setup testing functionality for dummy instruments."""
        if hasattr(self._node, 'port') and 'dummy' in str(self._node.port).lower():
            # This is a dummy instrument, add a test method
            print(f"Setting up dummy testing for {self._node.port}")
            # You can enable extreme value testing by calling:
            # self._enable_extreme_testing(True)

    def _enable_extreme_testing(self, enabled=True, interval=10):
        """Enable extreme value testing on dummy instruments."""
        if not (hasattr(self._node, 'port') and 'dummy' in str(self._node.port).lower()):
            self._set_status("Extreme testing only available for dummy instruments", 
                           level="warn", timeout_ms=3000)
            return
            
        try:
            # Get the instrument from the manager
            instrument = self.manager.instrument(self._node.port, self._node.address)
            if hasattr(instrument, 'enable_extreme_test'):
                instrument.enable_extreme_test(enabled, interval)
                status = "enabled" if enabled else "disabled"
                self._set_status(f"Extreme value testing {status}", 
                               level="info", timeout_ms=3000)
                if enabled:
                    self._set_status(f"Will generate extreme values every {interval} measurements", 
                                   level="info", timeout_ms=5000)
            else:
                self._set_status("Extreme testing not supported by this instrument", 
                               level="warn", timeout_ms=3000)
        except Exception as e:
            self._set_status(f"Failed to configure extreme testing: {e}", 
                           level="error", timeout_ms=5000)

    def _init_status_timer(self):
        self._status_default_timeout_ms = 3000  # 3 seconds
        self._status_clear_timer = QtCore.QTimer(self)
        self._status_clear_timer.setSingleShot(True)
        self._status_clear_timer.timeout.connect(lambda: self.le_status.setText(""))


    def _set_status(
        self,
        text: str,
        *,
        value=None,
        unit: str = "",
        level: str = "info",
        timeout_ms: Optional[int] = None,
        fmt: str = None
    ):
        """Show a status message and optionally clear it.
        If `value` is given, appends ': <b>{value}</b> {unit}'.
        timeout_ms=None → use default; 0 → do not auto-clear.
        """
        styles = {
            "info":  "color: #2e7d32;",
            "warn":  "color: #e65100;",
            "error": "color: #b71c1c;",
            "":      ""
        }
        self.le_status.setStyleSheet(styles.get(level, ""))

        # optional value formatting
        suffix = ""
        if value is not None:
            if fmt is None:
                fmt = "{value:.2f}" if isinstance(value, float) else "{value}"
            try:
                val_str = fmt.format(value=value)
            except Exception:
                val_str = str(value)
            suffix = f"{val_str}{(' ' + unit) if unit else ' '}"

        self.le_status.setText(f"{text}{suffix}")

        # resolve timeout
        if timeout_ms is None:
            timeout_ms = getattr(self, "_status_default_timeout_ms", 3000)

        # start/skip timer safely
        self._status_clear_timer.stop()
        if timeout_ms:  # truthy: start; 0/False: don't auto-clear
            self._status_clear_timer.start(int(timeout_ms))

    def showEvent(self, ev):
        super().showEvent(ev)
        if not self._placed_once:
            parent = self.parent()
            if parent is not None and hasattr(parent, "tiler"):
                parent.tiler.place(self)
            self._placed_once = True

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
        self.ds_measure_flow.setMaximum(float(cap) if cap is not None else 1000)

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
        except Exception as e:
            self._set_status(f"Capacity error: {e}", level="error", timeout_ms=10000)
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
            raw_flow = float(f)
            
            # Validate flow measurement against instrument capacity
            capacity = getattr(self._node, "capacity", None)
            if capacity is not None:
                max_allowed = float(capacity) * 2.0  # 200% of capacity
                print(f"[MeterDialog] Flow measurement: {raw_flow:.2f}, Capacity: {capacity}, Max allowed: {max_allowed:.2f}")
                if raw_flow > max_allowed:
                    # Cap the measurement and show warning
                    capped_flow = max_allowed
                    warning_msg = f"Flow capped: {raw_flow:.1f} → {capped_flow:.1f} (>200% capacity)"
                    print(f"[MeterDialog] WARNING: {warning_msg}")
                    self._set_status(warning_msg, level="warn", timeout_ms=5000)
                    self._last_flow = capped_flow
                    self.ds_measure_flow.setValue(capped_flow)
                    self._update_flow_progress(capped_flow)
                else:
                    # Normal measurement within reasonable range
                    self._last_flow = raw_flow
                    self.ds_measure_flow.setValue(raw_flow)
                    self._update_flow_progress(raw_flow)
            else:
                print(f"[MeterDialog] No capacity defined for node, using raw flow: {raw_flow:.2f}")
                # No capacity info available, use raw measurement
                self._last_flow = raw_flow
                self.ds_measure_flow.setValue(raw_flow)
                self._update_flow_progress(raw_flow)

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
            self._set_status(f"Capacity error: {e}", level="error", timeout_ms=10000)
            cap = 0.0

        # QProgressBar is int-based → use tenths to keep 0.1 precision
        scale = 10
        maxv = int(round(cap * scale)) if cap > 0 else 1000  # fallback
        pb.setRange(0, maxv)

        val = float(round(max(0.0, min(flow, cap if cap > 0 else flow)) * scale))
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
        self._set_status(f"Fluid change failed: {msg}", level="error", timeout_ms=10000)
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
