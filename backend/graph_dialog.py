import pyqtgraph as pg
from pyqtgraph import TextItem
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
from PyQt5 import uic
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
import os, csv
from datetime import datetime, timedelta

class TimeAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        # If ISO mode, show ISO strings as weekday abbreviation and hour:minute
        if hasattr(self, 'iso_mode') and self.iso_mode and hasattr(self, 'iso_map') and self.iso_map:
            # Weekday abbreviations (German style)
            weekdays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
            labels = []
            for v in values:
                # Find closest ISO string for this tick value
                closest = min(self.iso_map, key=lambda tup: abs(tup[0] - v))
                dt = closest[1]
                wd = weekdays[dt.weekday()]
                labels.append(f"{wd} {dt.hour:02d}:{dt.minute:02d}")
            return labels
        # Otherwise, show seconds as before
        labels = []
        for v in values:
            if v < 60:
                labels.append(f"{int(v)}s")
            elif v < 3600:
                labels.append(f"{int(v//60)}m {int(v%60)}s")
            elif v < 86400:
                labels.append(f"{int(v//3600)}h {int((v%3600)//60)}m")
            else:
                labels.append(f"{int(v//86400)}d {int((v%86400)//3600)}h")
        return labels


class GraphDialog(QDialog):
    def __init__(self, parent=None, file_path=None):
        super().__init__(parent)
        self.file_path = file_path
        self.log_dir = os.path.join(os.getcwd(), "Data")  # Set log_dir to Data folder

        uic.loadUi("ui/graph.ui", self)

        layout = QVBoxLayout(self.frame)
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': TimeAxis(orientation='bottom')})
        layout.addWidget(self.plot_widget)
        self.frame.setLayout(layout)

        # Label axes
        self.plot_widget.setLabel('bottom', 'Time (s)', color='w', size='18pt')
        self.plot_widget.setLabel('left', 'Flow (other gases)', color='w', size='18pt')
        self.plot_widget.showAxis('right')
        self.plot_widget.getAxis('left').setTextPen('w')
        self.plot_widget.getAxis('bottom').setTextPen('w')
        self.plot_widget.getAxis('top').setTextPen('w')
        self.plot_widget.getAxis('right').setTextPen('w')

        # Create and link right ViewBox for H2
        self.right_viewbox = pg.ViewBox()
        self.plot_widget.scene().addItem(self.right_viewbox)
        self.plot_widget.getAxis('right').linkToView(self.right_viewbox)
        self.plot_widget.getAxis('right').setLabel('Flow (H\u2082)', color='w', size='18pt')

        # Overlay the right ViewBox on the main plot area
        self.plot_widget.getViewBox().sigResized.connect(
            lambda: self.right_viewbox.setGeometry(self.plot_widget.getViewBox().sceneBoundingRect())
        )

        # Synchronize x-axis range
        def updateViews():
            self.right_viewbox.setXRange(*self.plot_widget.getViewBox().viewRange()[0], padding=0)
        self.plot_widget.getViewBox().sigXRangeChanged.connect(updateViews)

        # Show grid lines
        self.plot_widget.showGrid(x=True, y=True)

        # Store data for plotting
        self.curves = {}
        self._setpoint_items = []
        self._axis_file_side = {}

        self._build_axis_assignment_ui()
        self._refresh_axis_assignment_list()

        # Connect UI controls
        self.pb_reload.clicked.connect(self.reload_data)
        self.pb_close.clicked.connect(self.close)
        self.cb_axis_linked.stateChanged.connect(self.toggle_axes_link)
        self.cb_time.addItems(["Full", "24 hours", "8 hours", "4 hours", "1 hour"])
        self.cb_time.currentIndexChanged.connect(self.on_time_range_changed)
        self.cb_ts_iso.addItems(["Timestamp", "ISO"])
        self.cb_ts_iso.currentIndexChanged.connect(self.reload_data)

    def _build_axis_assignment_ui(self):
        self.lbl_axis_assign = QLabel("Right axis files (unchecked = left axis)")
        self.lst_axis_assign = QListWidget()
        self.lst_axis_assign.setAlternatingRowColors(True)
        self.lst_axis_assign.setSelectionMode(QListWidget.NoSelection)
        self.lst_axis_assign.itemChanged.connect(lambda _item: self.reload_data())
        if hasattr(self, "gridLayout"):
            self.gridLayout.addWidget(self.lbl_axis_assign, 3, 0, 1, 3)
            self.gridLayout.addWidget(self.lst_axis_assign, 4, 0, 1, 3)

    def _list_csv_files(self):
        if not os.path.isdir(self.log_dir):
            return []
        return sorted([f for f in os.listdir(self.log_dir) if f.endswith(".csv")])

    def _refresh_axis_assignment_list(self):
        if not hasattr(self, "lst_axis_assign"):
            return

        # Preserve current check states before repopulating.
        for i in range(self.lst_axis_assign.count()):
            item = self.lst_axis_assign.item(i)
            if item is None:
                continue
            self._axis_file_side[item.text()] = (item.checkState() == Qt.Checked)

        self.lst_axis_assign.blockSignals(True)
        self.lst_axis_assign.clear()
        for fname in self._list_csv_files():
            item = QListWidgetItem(fname)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            on_right = bool(self._axis_file_side.get(fname, False))
            item.setCheckState(Qt.Checked if on_right else Qt.Unchecked)
            self.lst_axis_assign.addItem(item)
        self.lst_axis_assign.blockSignals(False)

    def _is_file_on_right_axis(self, fname: str) -> bool:
        if hasattr(self, "lst_axis_assign"):
            for i in range(self.lst_axis_assign.count()):
                item = self.lst_axis_assign.item(i)
                if item and item.text() == fname:
                    return item.checkState() == Qt.Checked
        return bool(self._axis_file_side.get(fname, False))
    
    def on_time_range_changed(self, idx):
        # Get all x values from all curves
        all_x = []
        for curve in self.curves.values():
            if hasattr(curve, 'xData') and curve.xData is not None:
                all_x.extend(curve.xData)
            elif hasattr(curve, 'getData'):  # fallback for PlotCurveItem
                x, _ = curve.getData()
                if x is not None:
                    all_x.extend(x)
        if not all_x:
            return
        min_x = min(all_x)
        max_x = max(all_x)
        # Combobox index: 0=Full, 1=24h, 2=8h, 3=4h, 4=1h
        hours = [None, 24, 8, 4, 1][idx]
        if hours is None:
            self.plot_widget.setXRange(min_x, max_x, padding=0)
            self.right_viewbox.setXRange(min_x, max_x, padding=0)
        else:
            cutoff = max_x - hours * 3600
            self.plot_widget.setXRange(cutoff, max_x, padding=0)
            self.right_viewbox.setXRange(cutoff, max_x, padding=0)
        # If a file_path is provided, load it
        if self.file_path:
            self.load_file(self.file_path)
    
    def toggle_axes_link(self, state):
        if state:  # Checked, link axes
            self.right_viewbox.setYLink(self.plot_widget.getViewBox())
        else:      # Unchecked, unlink axes
            self.right_viewbox.setYLink(None)
            # Optionally, reset y-ranges for each axis
            # self.right_viewbox.setYRange(...)
            # self.plot_widget.getViewBox().setYRange(...)
    
    def parse_log_file(self, log_path, use_iso, fname):
        data_x_raw, data_y = [], []
        setpoint_x_raw, setpoint_y = [], []
        usertag = fname
        try:
            with open(log_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("kind") == "measure" and row.get("name") == "fMeasure":
                        if use_iso:
                            dt = datetime.fromisoformat(row["iso"])
                            data_x_raw.append(dt)
                        else:
                            ts = float(row["ts"])
                            data_x_raw.append(ts)
                        value = float(row["value"])
                        data_y.append(value)
                        usertag = row.get("usertag", fname)
                    elif row.get("kind") == "setpoint" and row.get("name") == "fSetpoint":
                        if use_iso:
                            dt = datetime.fromisoformat(row["iso"])
                            setpoint_x_raw.append(dt)
                        else:
                            ts = float(row["ts"])
                            setpoint_x_raw.append(ts)
                        value = float(row["value"])
                        setpoint_y.append(value)
        except Exception as e:
            print(f"Error loading {fname}: {e}")
        return data_x_raw, data_y, setpoint_x_raw, setpoint_y, usertag

    def convert_times(self, data_x_raw, setpoint_x_raw, use_iso):
        iso_map = []
        if data_x_raw:
            t0 = data_x_raw[0]
            if use_iso:
                data_x = [(dt - t0).total_seconds() for dt in data_x_raw]
                iso_map = list(zip(data_x, data_x_raw))
            else:
                data_x = [t - t0 for t in data_x_raw]
        else:
            data_x = []
        if setpoint_x_raw and data_x_raw:
            t0 = data_x_raw[0]
            if use_iso:
                setpoint_x = [(dt - t0).total_seconds() for dt in setpoint_x_raw]
            else:
                setpoint_x = [t - t0 for t in setpoint_x_raw]
        else:
            setpoint_x = []
        return data_x, setpoint_x, iso_map

    def plot_curve(self, data_x, data_y, usertag, color, on_right_axis=False, curve_key=None):
        if on_right_axis:
            curve = pg.PlotCurveItem(data_x, data_y, pen=color, name=usertag)
            self.right_viewbox.addItem(curve)
        else:
            curve = self.plot_widget.plot(data_x, data_y, pen=color, name=usertag)
        self.curves[curve_key or usertag] = curve
        # Force minimum to zero for the axis
        if data_y:
            target_viewbox = self.right_viewbox if on_right_axis else self.plot_widget.getViewBox()
            target_viewbox.setYRange(0, max(data_y), padding=0.1)
        return curve

    def plot_setpoints(self, setpoint_x, setpoint_y, usertag, color, on_right_axis=False):
        if setpoint_x and setpoint_y:
            scatter = pg.ScatterPlotItem(
                x=setpoint_x,
                y=setpoint_y,
                pen=color,
                brush=color,
                symbol='o',
                size=12,
                name=f'{usertag} setpoint'
            )
            if on_right_axis:
                self.right_viewbox.addItem(scatter)
            else:
                self.plot_widget.addItem(scatter)
            self._setpoint_items.append((scatter, on_right_axis))

    def add_curve_label(self, data_x, data_y, usertag, color, on_right_axis=False):
        if data_x and data_y:
            label = TextItem(usertag, color=color, anchor=(0.5, 1.0), border='w', fill=(0,0,0,150))
            target_viewbox = self.right_viewbox if on_right_axis else self.plot_widget
            target_viewbox.addItem(label)
            y_offset = 0.05 * (max(data_y) - min(data_y) if len(data_y) > 1 else 1)
            label.setPos(data_x[-1], data_y[-1] + y_offset)
            if on_right_axis:
                self._textitems_right.append(label)
            else:
                self._textitems_left.append(label)


    def load_file(self, path):
        try:
            with open(path, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                data = [row for row in reader]
                times = [float(row["ts"]) for row in data if row["kind"] == "measure"]
                values = [float(row["value"]) for row in data if row["kind"] == "measure"]
                #for row in data:
                #    print(row)
                # Example: extract time and value for plotting
                #times = [float(row["ts"]) for row in data if row["kind"] == "measure"]
                #values = [float(row["value"]) for row in data if row["kind"] == "measure"]
                # TODO: plot times vs values
        except Exception as e:
            print(f"Error loading file: {e}")

    def add_point(self, x, y):
        self.data_x.append(x)
        self.data_y.append(y)
        self.curve.setData(self.data_x, self.data_y)
    
    def reload_data(self):
        self._refresh_axis_assignment_list()
        iso_map = []
        # Remove old curves
        for curve in self.curves.values():
            if curve in self.plot_widget.items():
                self.plot_widget.removeItem(curve)
            if curve in list(getattr(self.right_viewbox, 'addedItems', [])):
                self.right_viewbox.removeItem(curve)
        self.curves.clear()

        # Remove old setpoint markers
        for scatter, on_right in self._setpoint_items:
            if on_right:
                if scatter in list(getattr(self.right_viewbox, 'addedItems', [])):
                    self.right_viewbox.removeItem(scatter)
            else:
                if scatter in self.plot_widget.items():
                    self.plot_widget.removeItem(scatter)
        self._setpoint_items = []

        # Track and remove TextItems only from their parent viewbox
        if not hasattr(self, '_textitems_left'):
            self._textitems_left = []
        if not hasattr(self, '_textitems_right'):
            self._textitems_right = []
        for label in self._textitems_left:
            if label in self.plot_widget.items():
                self.plot_widget.removeItem(label)
        for label in self._textitems_right:
            if label in list(getattr(self.right_viewbox, 'addedItems', [])):
                self.right_viewbox.removeItem(label)
        self._textitems_left = []
        self._textitems_right = []

        use_iso = self.cb_ts_iso.currentIndex() == 1  # 0=Timestamp, 1=ISO

        vibrant_colors = [
            (255, 0, 0),    # Red
            (0, 255, 0),    # Green
            (0, 255, 255),  # Cyan
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 0, 255),    # Blue
            # Add more as needed
        ]

        global_max_y = float('-inf')  # Initialize global max value
        global_max_y_right = float('-inf')

        for fname in self._list_csv_files():
            log_path = os.path.join(self.log_dir, fname)
            data_x_raw, data_y, setpoint_x_raw, setpoint_y, usertag = self.parse_log_file(log_path, use_iso, fname)
            data_x, setpoint_x, file_iso_map = self.convert_times(data_x_raw, setpoint_x_raw, use_iso)
            color = vibrant_colors[len(self.curves) % len(vibrant_colors)]
            on_right_axis = self._is_file_on_right_axis(fname)
            display_name = f"{usertag} [{fname}]"
            curve_key = f"{fname}:{usertag}"
            self.plot_setpoints(setpoint_x, setpoint_y, display_name, color, on_right_axis=on_right_axis)
            self.plot_curve(data_x, data_y, display_name, color, on_right_axis=on_right_axis, curve_key=curve_key)
            self.add_curve_label(data_x, data_y, display_name, color, on_right_axis=on_right_axis)
            if use_iso:
                iso_map.extend(file_iso_map)

            if data_y:
                if on_right_axis:
                    global_max_y_right = max(global_max_y_right, max(data_y))
                else:
                    global_max_y = max(global_max_y, max(data_y))

        # Set axis mode and mapping for tickStrings
        axis = self.plot_widget.getAxis('bottom')
        axis.iso_mode = use_iso
        axis.iso_map = iso_map if use_iso else None

        self.plot_widget.showGrid(x=True, y=True)

        # Set the range of the left axis based on global_max_y
        if global_max_y > float('-inf'):  # Ensure there is valid data
            self.plot_widget.getViewBox().setYRange(0, global_max_y, padding=0.1)
        if global_max_y_right > float('-inf'):
            self.right_viewbox.setYRange(0, global_max_y_right, padding=0.1)
