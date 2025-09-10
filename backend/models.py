# propar_qt/models.py
from typing import List


from PyQt5.QtCore import (
Qt, QAbstractListModel, QAbstractTableModel, QModelIndex, QVariant
)


from .types import NodeInfo
from .manager import ProparManager


class NodesListModel(QAbstractListModel):
    def __init__(self, manager: ProparManager):
        super().__init__()
        self._mgr = manager
        self._nodes: List[NodeInfo] = []
        manager.nodeAdded.connect(self._onNode)


    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._nodes)


    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._nodes)):
            return None
        node = self._nodes[index.row()]
        if role == Qt.DisplayRole:
            return f"{node.port} | addr {node.address} | {node.dev_type} | {node.serial} | ch {node.channels}"
        return None


    def nodeAt(self, row: int):
        if 0 <= row < len(self._nodes):
            return self._nodes[row]
        return None


    def _onNode(self, info: NodeInfo):
        self.beginInsertRows(QModelIndex(), len(self._nodes), len(self._nodes))
        self._nodes.append(info)
        self.endInsertRows()




class NodesTableModel(QAbstractTableModel):
    HEADERS = ["Port", "Address", "Type", "Serial", "ID"]


    def __init__(self, manager: ProparManager):
        super().__init__()
        self._mgr = manager
        self._nodes: List[NodeInfo] = []
        manager.nodeAdded.connect(self._onNode)


    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._nodes)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section: int, orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return int(section + 1) if orientation == Qt.Vertical else None


    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        node = self._nodes[index.row()]
        col = index.column()
        if col == 0:
            return node.port
        if col == 1:
            return node.address
        if col == 2:
            return node.dev_type
        if col == 3:
            return node.serial
        if col == 4:
            return getattr(node, "number", None)
        return None


    def _onNode(self, info: NodeInfo):
        self.beginInsertRows(QModelIndex(), len(self._nodes), len(self._nodes))
        self._nodes.append(info)
        self.endInsertRows()