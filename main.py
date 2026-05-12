from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from controllers.main_controller import MainController
from utils.fonts import ui_font
from views.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(ui_font(10))
    window = MainWindow()
    controller = MainController(window)
    window.controller = controller
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
