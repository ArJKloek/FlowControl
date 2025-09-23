import pyqtgraph as pg
from PyQt5.QtWidgets import QDialog, QVBoxLayout
from PyQt5 import uic
import os, csv

class GraphDialog(QDialog):
    def __init__(self, parent=None, file_path=None):
        super().__init__(parent)
        self.file_path = file_path
        self.log_dir = os.path.join(os.getcwd(), "Data")  # Set log_dir to Data folder
    
        uic.loadUi("ui/graph.ui", self)
        

        layout = QVBoxLayout(self.frame)
        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)
        self.frame.setLayout(layout)

        # Add a PlotWidget to the frame
        #self.plot_widget = pg.PlotWidget(self.frame)
        #self.plot_widget.setGeometry(self.frame.rect())
        #self.plot_widget.show()
        
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
                data_x, data_y = [], []
                log_path = os.path.join(self.log_dir, fname)
                try:
                    with open(log_path, "r", newline="") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get("kind") == "measure" and row.get("name") == "fMeasure":
                                ts = float(row["ts"])
                                value = float(row["value"])
                                data_x.append(ts)
                                data_y.append(value)
                                usertag = row.get("usertag", fname)  # get usertag from row
                    # Add a new curve for this file
                    color = pg.intColor(len(self.curves))  # auto color
                    curve = self.plot_widget.plot(data_x, data_y, pen=color, name=usertag or fname)
                    self.curves[usertag or fname] = curve
                except Exception as e:
                    print(f"Error loading {fname}: {e}")