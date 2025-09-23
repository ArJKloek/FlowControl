from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout
from PyQt5.QtWebEngineWidgets import QWebEngineView
import plotly.graph_objs as go
import plotly.io as pio
import sys

class PlotlyDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plotly in PyQt")
        layout = QVBoxLayout(self)
        self.webview = QWebEngineView()
        layout.addWidget(self.webview)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[1,2,3], y=[4,5,6], mode='lines', name='Test'))
        fig.update_layout(title='Plotly Example')

        html = pio.to_html(fig, full_html=False)
        self.webview.setHtml(html)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    dlg = PlotlyDialog()
    dlg.show()
    sys.exit(app.exec_())