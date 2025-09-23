import pyqtgraph as pg
from pyqtgraph import TextItem
from PyQt5.QtWidgets import QDialog, QVBoxLayout
from PyQt5 import uic
from PyQt5.QtGui import QFont
import os, csv
from datetime import datetime, timedelta

class TimeAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        # Convert seconds to human-readable format
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
        #self.plot_widget.setLabel('right', 'Flow (H\u2082)', color='w', size='18pt')

        # Add a PlotWidget to the frame
        #self.plot_widget = pg.PlotWidget(self.frame)
        #self.plot_widget.setGeometry(self.frame.rect())
        #self.plot_widget.show()
        self.plot_widget.getAxis('left').setTextPen('w')
        self.plot_widget.getAxis('bottom').setTextPen('w')
        self.plot_widget.getAxis('top').setTextPen('w')
        self.plot_widget.showAxis('right')
        self.plot_widget.getAxis('right').setTextPen('w')
        
        # After creating self.plot_widget
        self.right_viewbox = pg.ViewBox()
        self.plot_widget.scene().addItem(self.right_viewbox)
        self.plot_widget.getAxis('right').linkToView(self.right_viewbox)
        self.plot_widget.getAxis('right').setLabel('Flow (H\u2082)', color='w', size='18pt')

        # Overlay the right ViewBox on the main plot area
        self.plot_widget.getViewBox().sigResized.connect(lambda: self.right_viewbox.setGeometry(self.plot_widget.getViewBox().sceneBoundingRect()))

        # Synchronize x-axis range
        def updateViews():
            self.right_viewbox.setXRange(*self.plot_widget.getViewBox().viewRange()[0], padding=0)
        self.plot_widget.getViewBox().sigXRangeChanged.connect(updateViews)

        # Store data for plotting
        self.curves = {}  # key: filename, value: curve object

        # Example: connect reload button
        self.pb_reload.clicked.connect(self.reload_data)
        self.pb_close.clicked.connect(self.close)
        self.cb_axis_linked.stateChanged.connect(self.toggle_axes_link)
        self.cb_time.addItems([
            "Full",
            "24 hours",
            "8 hours",
            "4 hours",
            "1 hour"
        ])
        self.cb_time.currentIndexChanged.connect(self.on_time_range_changed)
        self.cb_ts_iso.addItems(["Timestamp", "ISO"])
        self.cb_ts_iso.currentIndexChanged.connect(self.reload_data)
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
        # Remove old curves
        for curve in self.curves.values():
            if curve in self.plot_widget.items():
                self.plot_widget.removeItem(curve)
            if curve in list(getattr(self.right_viewbox, 'addedItems', [])):
                self.right_viewbox.removeItem(curve)
        self.curves.clear()
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

        for fname in os.listdir(self.log_dir):
            if fname.endswith(".csv"):
                data_x_raw, data_y = [], []
                log_path = os.path.join(self.log_dir, fname)
                try:
                    with open(log_path, "r", newline="") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get("kind") == "measure" and row.get("name") == "fMeasure":
                                if use_iso:
                                    print(f'iso: {row["iso"]}')
                                    # Convert ISO string to seconds since first entry
                                    dt = datetime.fromisoformat(row["iso"])
                                    data_x_raw.append(dt)
                                else:
                                    ts = float(row["ts"])
                                    data_x_raw.append(ts)
                                value = float(row["value"])
                                data_y.append(value)
                                usertag = row.get("usertag", fname)
                    if data_x_raw:
                        if use_iso:
                            t0 = data_x_raw[0]
                            data_x = [(dt - t0).total_seconds() for dt in data_x_raw]
                        else:
                            t0 = data_x_raw[0]
                            data_x = [t - t0 for t in data_x_raw]
                    else:
                        data_x = []
                    vibrant_colors = [
                        (255, 0, 0),    # Red
                        (0, 255, 0),    # Green
                        (0, 255, 255),  # Cyan
                        (255, 255, 0),  # Yellow
                        (255, 0, 255),  # Magenta
                        (0, 0, 255),    # Blue
                        # Add more as needed
                    ]
                    color = vibrant_colors[len(self.curves) % len(vibrant_colors)]
                    if usertag == "H2":
                        curve = pg.PlotCurveItem(data_x, data_y, pen=color, name=usertag)
                        self.right_viewbox.addItem(curve)
                        # Force minimum to zero for right axis
                        if data_y:
                            self.right_viewbox.setYRange(0, max(data_y), padding=0.1)
                        # Add label above the last point for H2 only in right axis
                        if data_x and data_y:
                            label = TextItem(usertag, color=color, anchor=(0.5, 1.0), border='w', fill=(0,0,0,150))
                            self.right_viewbox.addItem(label)
                            self._textitems_right.append(label)
                            y_offset = 0.05 * (max(data_y) - min(data_y) if len(data_y) > 1 else 1)
                            label.setPos(data_x[-1], data_y[-1] + y_offset)
                    else:
                        curve = self.plot_widget.plot(data_x, data_y, pen=color, name=usertag)
                        # Force minimum to zero for left axis
                        if data_y:
                            self.plot_widget.getViewBox().setYRange(0, max(data_y), padding=0.1)
                        # Add label above the last point for non-H2 curves only
                        if data_x and data_y:
                            label = TextItem(usertag or fname, color=color, anchor=(0.5, 1.0), border='w', fill=(0,0,0,150))
                            self.plot_widget.addItem(label)
                            self._textitems_left.append(label)
                            y_offset = 0.05 * (max(data_y) - min(data_y) if len(data_y) > 1 else 1)
                            label.setPos(data_x[-1], data_y[-1] + y_offset)
                    self.curves[usertag or fname] = curve

                except Exception as e:
                    print(f"Error loading {fname}: {e}")
