import sys
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout

app = QApplication(sys.argv)
window = QWidget()
window.setWindowTitle("北京交通大学就餐仿真系统")
layout = QVBoxLayout()
layout.addWidget(QLabel("Hello World，开发环境搭建成功"))
window.setLayout(layout)
window.resize(420, 180)
window.show()
sys.exit(app.exec())
