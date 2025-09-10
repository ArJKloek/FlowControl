# propar_qt/main.py
import sys
from PyQt5 import uic
from PyQt5.QtWidgets import (
QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QTextEdit, QTableView
)

from backend.manager import ProparManager
from backend.models import NodesTableModel
from dialogs import NodeViewer
from flowchannel import FlowChannelDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        uic.loadUi("ui/main.ui", self)

        self.manager = ProparManager()
        self.model = NodesTableModel(self.manager)

        self.actionOpen_scanner.triggered.connect(self.openNodeViewer)


    def openNodeViewer(self):
        dlg = NodeViewer(self.manager, self)
        #dlg.nodesSelected.connect(self.openFlowChannels)
        dlg.exec_()

    #def openFlowChannels(self, node_list):
    #    FlowChannelDialog(self.manager, node_list, self).exec_()

    
def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(900, 520)
    w.show()
    sys.exit(app.exec_())




if __name__ == "__main__":
    main()