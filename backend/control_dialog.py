from PyQt5.QtWidgets import QDialog, QLayout
from PyQt5.QtCore import Qt, QSignalBlocker
from PyQt5 import uic, QtCore
from PyQt5.QtGui import QPixmap
from typing import Optional
import time
from .constants import (
    UI_DIR,
    INTERACTION_POLL_SUSPEND_MS,
    STATUS_MESSAGE_TIMEOUT_MS,
    MEASURE_FLOW_UI_EPSILON,
    MEASURE_PERCENT_UI_EPSILON,
    SETPOINT_SLOPE_RAW_MAX,
)


from resources_rc import *  # Import the compiled resources








def _set_spin_if_idle(spin, value, tol=1e-6):
        # don’t overwrite while user is editing
        if spin.hasFocus():
            return
        with QSignalBlocker(spin):
            if abs(spin.value() - float(value)) > tol:
                spin.setValue(float(value))

def _set_slider_if_idle(slider, value):
    """
    Safely update a QSlider only when the user isn't dragging it.
    Accepts float or int; rounds to int for slider.
    """
    if slider.isSliderDown() or slider.hasFocus():
        return
    vi = int(round(float(value)))
    if slider.value() != vi:
        # QSlider doesn't emit valueChanged if value is the same, but let's be tidy:
        with QSignalBlocker(slider):
            slider.setValue(vi)

class ControllerDialog(QDialog):
    def __init__(self, manager, nodes, parent=None):
        super().__init__(parent)
        self.manager = manager
        uic.loadUi(str(UI_DIR / "flowchannel.ui"), self)
        # in your dialog __init__ after loadUi(...)

        self._placed_once = False  

        self._init_status_timer()

        self.layout().setSizeConstraint(QLayout.SetFixedSize)  # dialog follows sizeHint
        self.advancedFrame.setVisible(False)
        self.btnAdvanced.setCheckable(True)
        self.btnAdvanced.toggled.connect(self._toggle_advanced)
        if hasattr(self, 'debugFrame'):
            self.debugFrame.setVisible(False)
        if hasattr(self, 'pb_debug'):
            self.pb_debug.setCheckable(True)
            self.pb_debug.toggled.connect(self._toggle_debug)
        self.cb_fluids.currentIndexChanged.connect(self._on_fluid_selected)
        self._last_ts = None
        self._combo_active = False
        self.cb_fluids.installEventFilter(self)   # gate setpoint while this combo is active
        
        node = nodes[0] if isinstance(nodes, list) else nodes

        icon_path = ":/icon/massflow.png" if str(node.model).startswith("F") else ":/icon/massstream.png"
        pixmap = QPixmap(icon_path).scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lb_icon.setPixmap(pixmap)
       
        self._node = node
        self._is_updating_gasfactor_ui = False
        self._last_known_fsetpoint = None
        self._last_known_setpoint_pct = None
        self._last_known_setpoint_raw = None
        self._last_known_setpoint_slope = None
        self._last_sent_flow = None
        self._last_sent_pct_raw = None
        self._last_sent_slope = None

        # Subscribe to manager-level polling and register this node
        self.manager.measured.connect(self._on_poller_measured, type=QtCore.Qt.QueuedConnection | QtCore.Qt.UniqueConnection)
        self.manager.register_node_for_polling(self._node.port, self._node.address, period=1.0)

        # (optional) surface poller errors to the user
        self.manager.pollerError.connect(lambda m: self._set_status(f"Port error: {m}", level="error", timeout_ms=10000))
        
        # Initialize gas factor display if widget exists
        if hasattr(self, 'ds_gasfactor'):
            current_factor = self.manager.get_gas_factor(self._node.port, self._node.address)
            self.ds_gasfactor.setValue(current_factor)
            # Enable/disable based on device type (only DMFC supports gas factor)
            is_dmfc = getattr(self._node, 'ident_nr', None) == 7
            self.ds_gasfactor.setEnabled(is_dmfc)
            if not is_dmfc and hasattr(self, 'lb_gasfactor'):
                self.lb_gasfactor.setText("Gas Factor (DMFC only)")
                    

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

    def showEvent(self, ev):
        super().showEvent(ev)
        if not self._placed_once:
            parent = self.parent()
            if parent is not None and hasattr(parent, "tiler"):
                parent.tiler.place(self)
            self._placed_once = True
        
        # Refresh gas factor display from persistent storage
        self._refresh_gas_factor_display()

    def _init_status_timer(self):
        self._status_default_timeout_ms = STATUS_MESSAGE_TIMEOUT_MS
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
            timeout_ms = getattr(self, "_status_default_timeout_ms", STATUS_MESSAGE_TIMEOUT_MS)

        # start/skip timer safely
        self._status_clear_timer.stop()
        if timeout_ms:  # truthy: start; 0/False: don't auto-clear
            self._status_clear_timer.start(int(timeout_ms))


    def eventFilter(self, obj, ev):
        if obj is self.cb_fluids:
            if ev.type() == QtCore.QEvent.FocusIn:
                self._combo_active = True
                # pause any pending send while user is in the combo
                self._sp_timer.stop()
            elif ev.type() == QtCore.QEvent.FocusOut:
                self._combo_active = False
                # user finished with the combo -> send the last pending setpoint target (if any)
                if getattr(self, "_pending_pct", None) is not None:
                    self._start_setpoint_ramp(int(self._pending_pct))
                    self._pending_pct = None
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
        if hasattr(self, 'comboBox'):
            self.comboBox.setCurrentIndex(0)
        if hasattr(self, 'sb_slopefactor'):
            self.sb_slopefactor.setRange(0, int(SETPOINT_SLOPE_RAW_MAX))
            if self.sb_slopefactor.value() <= 0:
                self.sb_slopefactor.setValue(0)  # default disabled; 0 means immediate setpoint
        self._populate_fluids(node)  # <-- add this
        # --- Setpoint wiring ---
        # Create timers and internal state only once to avoid duplicate timers/connections
        if not hasattr(self, '_sp_timer'):
            self._sp_guard = False                      # prevents feedback loops
            self._pending_flow = None                   # last requested flow setpoint
            self._sp_timer = QtCore.QTimer(self)        # debounce so we don't spam the bus
            self._sp_timer.setSingleShot(True)
            self._sp_timer.setInterval(INTERACTION_POLL_SUSPEND_MS)
            self._sp_timer.timeout.connect(self._send_setpoint_flow)

        if not hasattr(self, '_sp_pct_timer'):
            self._pending_pct = None                   # last requested percent setpoint
            self._sp_pct_timer = QtCore.QTimer(self)        # debounce so we don't spam the bus
            self._sp_pct_timer.setSingleShot(True)
            self._sp_pct_timer.setInterval(INTERACTION_POLL_SUSPEND_MS)
            self._sp_pct_timer.timeout.connect(self._send_setpoint_pct)

        if not hasattr(self, '_sp_slope_timer'):
            self._pending_slope = None
            self._sp_slope_timer = QtCore.QTimer(self)
            self._sp_slope_timer.setSingleShot(True)
            self._sp_slope_timer.setInterval(INTERACTION_POLL_SUSPEND_MS)
            self._sp_slope_timer.timeout.connect(self._send_setpoint_slope)

        if not hasattr(self, '_ramp_timer'):
            self._ramp_timer = QtCore.QTimer(self)
            self._ramp_timer.setInterval(100)  # 0.1s update cadence
            self._ramp_timer.timeout.connect(self._on_ramp_tick)
            self._ramp_active = False
            self._ramp_start_raw = None
            self._ramp_target_raw = None
            self._ramp_duration_sec = 0.0
            self._ramp_started_at = 0.0
            self._ramp_last_sent_raw = None

        if not hasattr(self, '_usertag_timer'):
            self._pending_usertag = None                   # last requested usertag
            self._usertag_timer = QtCore.QTimer(self)        # debounce so we don't spam the bus
            self._usertag_timer.setSingleShot(True)
            self._usertag_timer.setInterval(INTERACTION_POLL_SUSPEND_MS)
            self._usertag_timer.timeout.connect(self._send_usertag)

        # Connect widget signals once. Disconnect first to avoid duplicate connections
        try:
            self.ds_setpoint_flow.editingFinished.disconnect(self._on_sp_flow_changed)
        except Exception:
            pass
        self.ds_setpoint_flow.editingFinished.connect(self._on_sp_flow_changed)

        try:
            self.ds_setpoint_percent.editingFinished.disconnect(self._on_sp_percent_changed)
        except Exception:
            pass
        self.ds_setpoint_percent.editingFinished.connect(self._on_sp_percent_changed)

        try:
            self.vs_setpoint.sliderReleased.disconnect(self._on_sp_slider_changed)
        except Exception:
            pass
        self.vs_setpoint.sliderReleased.connect(self._on_sp_slider_changed)

        try:
            self.le_usertag.editingFinished.disconnect(self._on_usertag_changed)
        except Exception:
            pass
        self.le_usertag.editingFinished.connect(self._on_usertag_changed)

        if hasattr(self, 'sb_slopefactor'):
            try:
                self.sb_slopefactor.editingFinished.disconnect(self._on_slope_changed)
            except Exception:
                pass
            self.sb_slopefactor.editingFinished.connect(self._on_slope_changed)

        if hasattr(self, 'comboBox'):
            try:
                self.comboBox.currentIndexChanged.disconnect(self._on_slope_changed)
            except Exception:
                pass
            self.comboBox.currentIndexChanged.connect(self._on_slope_changed)

        try:
            self.ds_setpoint_percent.valueChanged.disconnect(self._on_sp_percent_live)
        except Exception:
            pass
        self.ds_setpoint_percent.valueChanged.connect(self._on_sp_percent_live)
        
        # Gas factor connection (if the widget exists)
        if hasattr(self, 'ds_gasfactor'):
            # Configure the widget for proper typing
            self.ds_gasfactor.setRange(0.1, 5.0)  # Set proper range
            self.ds_gasfactor.setDecimals(3)      # Allow 3 decimal places
            self.ds_gasfactor.setSingleStep(0.001)  # Step by 0.001 for fine control
            self.ds_gasfactor.setKeyboardTracking(True)  # Enable keyboard input
            self.ds_gasfactor.setFocusPolicy(Qt.StrongFocus)  # Allow focus

            try:
                self.ds_gasfactor.editingFinished.disconnect(self._on_gas_factor_changed)
            except Exception:
                pass
            self.ds_gasfactor.editingFinished.connect(self._on_gas_factor_changed)

            try:
                self.ds_gasfactor.valueChanged.disconnect(self._on_gas_factor_value_changed)
            except Exception:
                pass
            # Also connect valueChanged as backup for immediate feedback
            self.ds_gasfactor.valueChanged.connect(self._on_gas_factor_value_changed)
            # Load existing gas factor if available
            if self._node:
                existing_factor = self.manager.get_gas_factor(self._node.port, self._node.address, getattr(self._node, 'serial', None))
                self.ds_gasfactor.setValue(existing_factor)
                
                # Enable/disable based on device type
                self._update_gas_factor_state()

        # and stop sending on every incremental change:
        #self.sb_setpoint_flow.valueChanged.disconnect(self._on_sp_flow_changed)
        #self.sb_setpoint_percent.valueChanged.disconnect(self._on_sp_percent_changed)
        # initialize ranges from capacity, if available
        self._apply_capacity_limits()
    
   
    


    def _on_usertag_changed(self, usertag=None):
        if usertag is None:
            usertag = self.le_usertag.text().strip()
        self._pending_usertag = str(usertag)
        if self._combo_active:
            # defer until combo is deselected
            self._usertag_timer.stop()
        else:
            self._usertag_timer.start()

    def _slope_raw_to_seconds(self, raw_value) -> float:
        try:
            raw_value = float(raw_value)
        except Exception:
            return 0.0
        return max(0.0, raw_value) * 0.1

    def _current_slope_seconds(self) -> float:
        if not hasattr(self, 'sb_slopefactor'):
            return 0.0
        try:
            factor = max(0.0, float(self.sb_slopefactor.value()))
        except Exception:
            return 0.0

        mult = 1.0
        if hasattr(self, 'comboBox'):
            idx = int(self.comboBox.currentIndex())
            if idx == 1:
                mult = 60.0
            elif idx == 2:
                mult = 3600.0
            elif idx == 3:
                mult = 86400.0
        return factor * mult

    def _on_slope_changed(self, slope_val=None):
        if not hasattr(self, 'sb_slopefactor'):
            return

        if slope_val is None:
            slope_val = self.sb_slopefactor.value()

        try:
            slope_val = float(slope_val)
        except Exception:
            return

        slope_seconds = self._current_slope_seconds()
        self._set_status("Ramp slope configured", value=slope_seconds, unit="s (0-100%)", fmt="{value:.1f}")
    
    
        # fluid change wiring
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
        self._queue_setpoint_pct(float(val))
    
    def _on_sp_flow_changed(self, flow_val=None):
        if flow_val is None: 
            flow_val = self.ds_setpoint_flow.value()

        try:
            flow_val = float(flow_val)
        except Exception:
            return

        reference_flow = self._last_known_fsetpoint
        if reference_flow is None:
            reference_flow = self._last_sent_flow

        if reference_flow is not None and abs(flow_val - float(reference_flow)) <= MEASURE_FLOW_UI_EPSILON:
            return

        if self._pending_flow is not None and abs(float(self._pending_flow) - flow_val) <= MEASURE_FLOW_UI_EPSILON:
            return

        cap = getattr(self._node, 'capacity', None)
        if cap is None or float(cap) <= 0:
            return

        pct_val = max(0.0, min(100.0, (float(flow_val) / float(cap)) * 100.0))
        self._queue_setpoint_pct(pct_val)
    
    def _update_setpoint_enabled_state(self):
        # Decide from node.dev_type or the UI field (case-insensitive)
        t = (str(getattr(self._node, "dev_type", "")) or self.le_type.text() or "").strip().upper()
        self._is_meter = (t == "DMFM")  # adjust if you have variants like "DMFM-xxx"

        enabled = not self._is_meter
        # Disable the setpoint widgets (flow, %, slider)
        for w in (self.ds_setpoint_flow, self.ds_setpoint_percent, self.vs_setpoint):
            w.setEnabled(enabled)
        if hasattr(self, 'sb_slopefactor'):
            self.sb_slopefactor.setEnabled(enabled)
        if hasattr(self, 'comboBox'):
            self.comboBox.setEnabled(enabled)
        # If you actually have a *setpoint combobox*, disable it too (optional):
        if hasattr(self, "cb_setpoint"):
            self.cb_setpoint.setEnabled(enabled)

        # If we’re disabling, cancel any pending write
        if not enabled and hasattr(self, "_sp_timer"):
            self._sp_timer.stop()
        if not enabled and hasattr(self, '_sp_pct_timer'):
            self._sp_pct_timer.stop()
        if not enabled and hasattr(self, '_sp_slope_timer'):
            self._sp_slope_timer.stop()
        if not enabled and hasattr(self, '_ramp_timer'):
            self._ramp_timer.stop()
            self._ramp_active = False

    def _queue_setpoint_pct(self, pct_val: float):
        # clamp to 0..100, convert to raw 0..32000 (int)
        pct_val = max(0.0, min(100.0, float(pct_val)))

        if self._last_known_setpoint_pct is not None:
            if abs(pct_val - float(self._last_known_setpoint_pct)) <= MEASURE_PERCENT_UI_EPSILON:
                return

        raw = int(round(pct_val * 32000.0 / 100.0))

        if self._last_sent_pct_raw is not None and int(self._last_sent_pct_raw) == raw and not getattr(self, '_ramp_active', False):
            return

        if self._combo_active:
            self._pending_pct = raw
            return

        self._start_setpoint_ramp(raw)

    def _start_setpoint_ramp(self, target_raw: int):
        target_raw = max(0, min(32000, int(target_raw)))
        current_raw = None
        if self._last_known_setpoint_raw is not None:
            current_raw = int(self._last_known_setpoint_raw)
        elif self._last_sent_pct_raw is not None:
            current_raw = int(self._last_sent_pct_raw)

        if current_raw is None:
            current_raw = target_raw

        if int(current_raw) == int(target_raw):
            return

        duration_sec = self._current_slope_seconds()
        if duration_sec <= 0:
            self.manager.request_setpoint_pct(self._node.port, self._node.address, float(target_raw))
            self._last_sent_pct_raw = int(target_raw)
            return

        # Emit one slope log entry at ramp start.
        self.manager.telemetry.emit({
            "ts": time.time(),
            "port": self._node.port,
            "address": self._node.address,
            "kind": "setpoint",
            "name": "fSetpointSlope",
            "value": round(float(duration_sec), 3),
            "unit": "s",
            "extra": f"setpoint_change_time_sec={duration_sec:.3f}",
        })

        start_flow = self._last_known_fsetpoint
        if start_flow is None:
            try:
                cap = float(getattr(self._node, "capacity", 0.0) or 0.0)
                if cap > 0:
                    start_flow = (float(current_raw) / 32000.0) * cap
            except Exception:
                start_flow = None
        if start_flow is not None:
            self.manager.telemetry.emit({
                "ts": time.time(),
                "port": self._node.port,
                "address": self._node.address,
                "kind": "setpoint",
                "name": "fSetpoint",
                "value": round(float(start_flow), 3),
                "unit": getattr(self._node, "unit", ""),
                "extra": "slope_start_current_setpoint",
            })

        self._ramp_active = True
        self._ramp_start_raw = int(current_raw)
        self._ramp_target_raw = int(target_raw)
        self._ramp_duration_sec = float(duration_sec)
        self._ramp_started_at = time.monotonic()
        self._ramp_last_sent_raw = None
        if not self._ramp_timer.isActive():
            self._ramp_timer.start()
        self._on_ramp_tick()

    def _on_ramp_tick(self):
        if not getattr(self, '_ramp_active', False):
            if hasattr(self, '_ramp_timer') and self._ramp_timer.isActive():
                self._ramp_timer.stop()
            return

        elapsed = max(0.0, time.monotonic() - float(self._ramp_started_at))
        duration = max(1e-9, float(self._ramp_duration_sec))
        frac = min(1.0, elapsed / duration)
        next_raw = int(round(self._ramp_start_raw + (self._ramp_target_raw - self._ramp_start_raw) * frac))

        if self._ramp_last_sent_raw is None or int(self._ramp_last_sent_raw) != int(next_raw):
            self.manager.request_setpoint_pct(self._node.port, self._node.address, float(next_raw), emit_log=False)
            self._last_sent_pct_raw = int(next_raw)
            self._ramp_last_sent_raw = int(next_raw)

        if frac >= 1.0 or int(next_raw) == int(self._ramp_target_raw):
            self._ramp_active = False
            end_flow = None
            if hasattr(self, "ds_setpoint_flow"):
                try:
                    end_flow = float(self.ds_setpoint_flow.value())
                except Exception:
                    end_flow = None
            if end_flow is None:
                try:
                    cap = float(getattr(self._node, "capacity", 0.0) or 0.0)
                    if cap > 0:
                        end_flow = (float(self._ramp_target_raw) / 32000.0) * cap
                except Exception:
                    end_flow = None
            if end_flow is not None:
                self.manager.telemetry.emit({
                    "ts": time.time(),
                    "port": self._node.port,
                    "address": self._node.address,
                    "kind": "setpoint",
                    "name": "fSetpoint",
                    "value": round(float(end_flow), 3),
                    "unit": getattr(self._node, "unit", ""),
                    "extra": "slope_end_target_setpoint",
                })
            if self._ramp_timer.isActive():
                self._ramp_timer.stop()

    def _on_sp_percent_live(self, pct_val: float):
        # called on every step/keypress; debounced by the timer
        self._queue_setpoint_pct(pct_val)

    def _on_sp_percent_changed(self, pct_val=None):
        # keeps your existing editingFinished path working too
        if pct_val is None:
            pct_val = self.ds_setpoint_percent.value()
        self._queue_setpoint_pct(pct_val)


    #def _on_sp_percent_changed(self, pct_val=None):
    #    if pct_val is None:
    #        pct_val = self.ds_setpoint_percent.value()
    #    new_val = (pct_val/100)*32000  # convert pct to raw

    #    # queue the write (debounced)
    #    self._pending_pct = float(new_val)

    #    #print("pct change input:", self._pending_pct)
    #    if self._combo_active:
    #        self._sp_pct_timer.stop()
    #    else:
    #        self._sp_pct_timer.start()

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
            self._last_sent_flow = float(self._pending_flow)
            self._set_status("Setpoint updated", value=self._pending_flow, unit=self._node.unit)

        except Exception as e:
            self._set_status(f"Setpoint error: {e}", level="error", timeout_ms=10000)

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
            self._last_sent_pct_raw = int(round(float(self._pending_pct)))
            self._set_status("Setpoint updated", value=((self._pending_pct/32000)*100), unit="%")

        except Exception as e:
            self._set_status(f"Setpoint error: {e}", level="error", timeout_ms=10000)

    def _send_setpoint_slope(self):
        """Deprecated: parameter 10 slope writes are disabled in favor of local ramping."""
        return

    def _send_usertag(self):
        """Actually send the setpoint via the manager/poller (serialized with polling)."""
        try:
            if self._pending_usertag is None:
                return
            self.manager.request_usertag(
                self._node.port,
                self._node.address,
                str(self._pending_usertag)
            )
        except Exception as e:
            self._set_status(f"Usertag error: {e}", level="error", timeout_ms=10000)





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
        setpslope = d.get("setpslope")
        fsetpoint = d.get("fsetpoint")
        # Calculate percentages
        measure_pct = (float(measure) / 32000 * 100) if measure is not None else None
        setpoint_pct = (float(setpoint) / 32000 * 100) if setpoint is not None else None

        # Display in spinboxes or labels
        if measure_pct is not None and hasattr(self, "ds_measure_percent"):
            self.ds_measure_percent.setValue(measure_pct)
        
        
        # Don't update setpoint controls if a ramp is active (keep UI frozen at target)
        ramp_active = getattr(self, '_ramp_active', False)
        
        if fsetpoint is not None and hasattr(self, "ds_setpoint_flow") and not ramp_active:
            _set_spin_if_idle(self.ds_setpoint_flow, float(fsetpoint))
            self._last_known_fsetpoint = float(fsetpoint)
        

        if setpoint_pct is not None and hasattr(self, "ds_setpoint_percent") and not ramp_active:
            _set_spin_if_idle(self.ds_setpoint_percent, float(setpoint_pct))
            self._last_known_setpoint_pct = float(setpoint_pct)
        if setpoint is not None:
            try:
                self._last_known_setpoint_raw = int(float(setpoint))
            except Exception:
                pass
        
            #if setpoint_pct is not None and hasattr(self, "ds_setpoint_percent"):
        #    self.ds_setpoint_percent.setValue(setpoint_pct)
        
        
        if measure_pct is not None and hasattr(self, "vs_measure"):
            self.vs_measure.setValue(float(measure_pct))

        
        if setpoint_pct is not None and hasattr(self, "vs_setpoint") and not ramp_active:
            _set_slider_if_idle(self.vs_setpoint, setpoint_pct)

        if setpslope is not None:
            try:
                self._last_known_setpoint_slope = int(setpslope)
            except Exception:
                pass
        
        if f is not None:
            #self.le_measure_flow.setText("{:.3f}".format(float(f)))
            self.ds_measure_flow.setValue(float(f))
        nm = d.get("name")
        if nm:
            self.le_fluid.setText(str(nm))
        
        # Update node device information if available
        ident_nr = d.get("ident_nr")
        device_category = d.get("device_category")
        if ident_nr is not None:
            old_ident = getattr(self._node, 'ident_nr', None)
            self._node.ident_nr = ident_nr
            # Update gas factor widget state if device type changed
            if old_ident != ident_nr:
                self._update_gas_factor_state()
        
        # Always refresh gas factor display for DMFC devices (in case it was loaded from persistent storage)
        if hasattr(self, 'ds_gasfactor') and getattr(self._node, 'ident_nr', None) == 7:
            current_factor = self.manager.get_gas_factor(self._node.port, self._node.address, getattr(self._node, 'serial', None))
            if (not self.ds_gasfactor.hasFocus()) and abs(self.ds_gasfactor.value() - current_factor) > 0.001:  # Only update if different and not during edit
                self.ds_gasfactor.setValue(current_factor)
        
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
        # Temporarily suppress setpoint activity to avoid triggering editingFinished
        try:
            self._suppress_setpoint_activity(True)
        except Exception:
            pass

        self.advancedFrame.setVisible(checked)
        self._adjust_dialog_size()  # grow/shrink the window to fit

        # Re-enable setpoint activity after layout settles
        QtCore.QTimer.singleShot(200, lambda: self._suppress_setpoint_activity(False))

    def _toggle_debug(self, checked):
        # Temporarily suppress setpoint activity to avoid triggering editingFinished
        try:
            self._suppress_setpoint_activity(True)
        except Exception:
            pass

        if hasattr(self, 'debugFrame'):
            self.debugFrame.setVisible(bool(checked))
        self._adjust_dialog_size()

        # Re-enable setpoint activity after layout settles
        QtCore.QTimer.singleShot(200, lambda: self._suppress_setpoint_activity(False))

    def _adjust_dialog_size(self):
        try:
            self.layout().invalidate()
            self.layout().activate()
        except Exception:
            pass
        self.adjustSize()

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

    def _suppress_setpoint_activity(self, disable: bool):
        """Block or unblock setpoint widget signals and stop pending timers.
        When disabling, stop debounce timers to prevent queued sends; when
        enabling, simply unblock signals (timers continue on next user input).
        """
        widgets = getattr(self, '__dict__', {})
        # Stop timers when disabling to avoid delayed sends during UI change
        try:
            if disable:
                if hasattr(self, '_sp_timer'):
                    self._sp_timer.stop()
                if hasattr(self, '_sp_pct_timer'):
                    self._sp_pct_timer.stop()
                if hasattr(self, '_sp_slope_timer'):
                    self._sp_slope_timer.stop()
                if hasattr(self, '_ramp_timer'):
                    self._ramp_timer.stop()
                    self._ramp_active = False
                if hasattr(self, '_usertag_timer'):
                    self._usertag_timer.stop()
        except Exception:
            pass

        # Block/unblock signals on the widgets we care about
        for name in ('ds_setpoint_flow', 'ds_setpoint_percent', 'vs_setpoint', 'sb_slopefactor', 'comboBox', 'le_usertag'):
            w = getattr(self, name, None)
            if w is None:
                continue
            try:
                w.blockSignals(bool(disable))
            except Exception:
                pass
    
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

    def _on_gas_factor_changed(self):
        """Handle gas factor changes from UI"""
        if not hasattr(self, 'ds_gasfactor'):
            return

        if self._is_updating_gasfactor_ui:
            return
            
        if not self._node:
            return
            
        current_value = self.ds_gasfactor.value()
        
        # Only allow gas factor for DMFC devices.
        # Use ident_nr when available, otherwise fall back to dev_type to avoid false reset early in dialog lifecycle.
        ident_nr = getattr(self._node, 'ident_nr', None)
        dev_type = str(getattr(self._node, 'dev_type', '')).upper()
        is_dmfc = (ident_nr == 7) or ('DMFC' in dev_type)
        if not is_dmfc:
            # Do not force-reset user value here; just inform.
            self._set_status("Gas factor only applies to DMFC devices", level="warn", timeout_ms=3000)
            return
            
        try:
            factor = float(current_value)
            
            # Validate factor range (0.1 to 5.0 to match UI maximum)
            if factor < 0.1 or factor > 5.0:
                self.ds_gasfactor.setValue(1.0)
                self._set_status("Gas factor must be between 0.1 and 5.0", level="error", timeout_ms=5000)
                return

            existing_factor = self.manager.get_gas_factor(
                self._node.port,
                self._node.address,
                getattr(self._node, 'serial', None)
            )
            if abs(float(existing_factor) - factor) <= 1e-9:
                return
                
            # Store in manager
            self.manager.set_gas_factor(self._node.port, self._node.address, factor, getattr(self._node, 'serial', None))
            self._set_status(f"Gas factor set to {factor:.3f}", level="info", timeout_ms=2000)
            
        except (ValueError, TypeError) as e:
            self._is_updating_gasfactor_ui = True
            self.ds_gasfactor.setValue(1.0)
            self._is_updating_gasfactor_ui = False
            self._set_status(f"Invalid gas factor value: {e}", level="error", timeout_ms=5000)

    def _on_gas_factor_value_changed(self, value):
        """Handle immediate gas factor value changes (backup handler)"""
        if self._is_updating_gasfactor_ui:
            return
        # Call the main handler after a short delay to avoid spam
        if hasattr(self, '_gas_factor_timer'):
            self._gas_factor_timer.stop()
        else:
            from PyQt5.QtCore import QTimer
            self._gas_factor_timer = QTimer()
            self._gas_factor_timer.setSingleShot(True)
            self._gas_factor_timer.timeout.connect(self._on_gas_factor_changed)
        self._gas_factor_timer.start(500)  # 500ms delay

    def _refresh_gas_factor_display(self):
        """Refresh the gas factor display from persistent storage"""
        if not hasattr(self, 'ds_gasfactor') or not self._node:
            return
            
        # Only for DMFC devices
        if getattr(self._node, 'ident_nr', None) == 7:
            current_factor = self.manager.get_gas_factor(
                self._node.port, 
                self._node.address, 
                getattr(self._node, 'serial', None)
            )
            if not self.ds_gasfactor.hasFocus():
                self._is_updating_gasfactor_ui = True
                self.ds_gasfactor.setValue(current_factor)
                self._is_updating_gasfactor_ui = False

    def _update_gas_factor_state(self):
        """Enable/disable gas factor widget based on device type"""
        if not hasattr(self, 'ds_gasfactor'):
            return
            
        if not self._node:
            self.ds_gasfactor.setEnabled(False)
            return
            
        # Only enable for DMFC devices; fall back to dev_type before ident_nr arrives.
        ident_nr = getattr(self._node, 'ident_nr', None)
        dev_type = str(getattr(self._node, 'dev_type', '')).upper()
        is_dmfc = (ident_nr == 7) or ('DMFC' in dev_type)
        self.ds_gasfactor.setEnabled(is_dmfc)
        
        # Also enable/disable the label if it exists
        if hasattr(self, 'lb_gasfactor'):
            self.lb_gasfactor.setEnabled(is_dmfc)
        
        if is_dmfc:
            # Ensure widget is properly configured for typing
            self.ds_gasfactor.setReadOnly(False)  # Make sure it's not read-only
            self.ds_gasfactor.setFocusPolicy(Qt.StrongFocus)  # Ensure it can receive focus
            # Load the current gas factor (refresh from persistent storage)
            current_factor = self.manager.get_gas_factor(self._node.port, self._node.address, getattr(self._node, 'serial', None))
            if not self.ds_gasfactor.hasFocus():
                self._is_updating_gasfactor_ui = True
                self.ds_gasfactor.setValue(current_factor)
                self._is_updating_gasfactor_ui = False
        else:
            self._is_updating_gasfactor_ui = True
            self.ds_gasfactor.setValue(1.0)
            self._is_updating_gasfactor_ui = False


