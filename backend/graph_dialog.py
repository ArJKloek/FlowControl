import pyqtgraph as pg
from PyQt5.QtWidgets import QDialog
from PyQt5 import uic

class GraphDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi("ui/graph.ui", self)
        
        # Add a PlotWidget to the frame
        self.plot_widget = pg.PlotWidget(self.frame)
        self.plot_widget.setGeometry(self.frame.rect())
        self.plot_widget.show()
        
        # Store data for plotting
        self.data_x = []
        self.data_y = []
        self.curve = self.plot_widget.plot(pen='y')
        
        # Example: connect reload button
        self.pushButton.clicked.connect(self.reload_data)
        self.pushButton_2.clicked.connect(self.close)
    
    def add_point(self, x, y):
        self.data_x.append(x)
        self.data_y.append(y)
        self.curve.setData(self.data_x, self.data_y)
    
    def reload_data(self):
        # Implement logic to reload or refresh data
        pass