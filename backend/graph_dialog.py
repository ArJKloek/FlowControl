import pyqtgraph as pg
from pyqtgraph import TextItem
from PyQt5.QtWidgets import QDialog, QVBoxLayout
from PyQt5 import uic
from PyQt5.QtGui import QFont
import os, csv

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
        self.plot_widget.addLegend()
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
        self.legend = self.plot_widget.addLegend()
        
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
        self.pushButton.clicked.connect(self.reload_data)
        self.pushButton_2.clicked.connect(self.close)

        # If a file_path is provided, load it
        if self.file_path:
            self.load_file(self.file_path)

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
            self.plot_widget.removeItem(curve)
        self.curves.clear()

        # Find all CSV log files in the directory
        for fname in os.listdir(self.log_dir):
            if fname.endswith(".csv"):
                data_x_raw, data_y = [], []
                log_path = os.path.join(self.log_dir, fname)
                try:
                    with open(log_path, "r", newline="") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get("kind") == "measure" and row.get("name") == "fMeasure":
                                ts = float(row["ts"])
                                value = float(row["value"])
                                data_x_raw.append(ts)
                                data_y.append(value)
                                usertag = row.get("usertag", fname)  # get usertag from row
                    # Shift time axis so it starts at zero
                    if data_x_raw:
                        t0 = data_x_raw[0]
                        data_x = [t - t0 for t in data_x_raw]
                    else:
                        data_x = []
                    # Add a new curve for this file
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
                    # In reload_data, when you detect H2
                    if usertag == "H2":
                        curve = pg.PlotCurveItem(data_x, data_y, pen=color, name=usertag)
                        self.right_viewbox.addItem(curve)
                        self.plot_widget.legend.addItem(curve, usertag)
                        # Force minimum to zero for right axis
                        if data_y:
                            self.right_viewbox.setYRange(0, max(data_y), padding=0.1)
                    else:
                        curve = self.plot_widget.plot(data_x, data_y, pen=color, name=usertag)
                        # Force minimum to zero for left axis
                        if data_y:
                            self.plot_widget.getViewBox().setYRange(0, max(data_y), padding=0.1)
                    if data_x and data_y:
                        # Place label above the last point
                        label = TextItem(usertag or fname, color=color, anchor=(0.5, 1.0), border='w', fill=(0,0,0,150))
                        self.plot_widget.addItem(label)
                        # Calculate a small offset above the last point
                        y_offset = 0.05 * (max(data_y) - min(data_y) if len(data_y) > 1 else 1)
                        label.setPos(data_x[-1], data_y[-1] + y_offset)
                                        
                    self.curves[usertag or fname] = curve

                except Exception as e:
                    print(f"Error loading {fname}: {e}")
