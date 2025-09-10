# propar_qt/types.py
from dataclasses import dataclass


@dataclass
class NodeInfo:
    port: str
    address: int
    dev_type: str
    serial: str
    id_str: str
    channels: int
    number: int