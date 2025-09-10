# propar_qt/main.py
import sys
from PyQt5 import uic
from PyQt5.QtWidgets import (
QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QTextEdit, QTableView
)

from backend.manager import ProparManager
from backend.models import NodesTableModel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        uic.loadUi("ui/main.ui", self)

        self.manager = ProparManager()
        self.model = NodesTableModel(self.manager)
    


    
def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(900, 520)
    w.show()
    sys.exit(app.exec_())




if __name__ == "__main__":
    main()