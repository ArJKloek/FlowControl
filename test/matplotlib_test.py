import sys
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt

class MatplotlibDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Matplotlib in PyQt")
        layout = QVBoxLayout(self)

        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        # Example plot
        x = [1, 2, 3, 4]
        y = [10, 20, 25, 30]
        self.ax.plot(x, y, label='Test Line')
        self.ax.set_xlabel('X Axis')
        self.ax.set_ylabel('Y Axis')
        self.ax.set_title('Matplotlib Example')
        self.ax.legend()
        self.ax.grid(True)
        self.canvas.draw()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    dlg = MatplotlibDialog()
    dlg.show()
    sys.exit(app.exec_())