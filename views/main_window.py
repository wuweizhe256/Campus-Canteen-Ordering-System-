from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from models.entities import RunSummary, SimulationConfig
from views.canvas_widget import CanvasWidget
from views.config_dialog import ConfigDialog
from views.stats_panel import StatsPanel


class MainWindow(QMainWindow):
    startRequested = pyqtSignal(object)
    stopRequested = pyqtSignal()
    pauseChanged = pyqtSignal(bool)
    timeScaleChanged = pyqtSignal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("校园食堂就餐仿真系统")
        self.resize(1280, 800)
        self._running = False
        self._paused = False

        self.canvas = CanvasWidget()
        self.stats_panel = StatsPanel()
        self.start_button = QPushButton("开始仿真")
        self.pause_button = QPushButton("暂停")
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.time_scale_label = QLabel("时间倍率 6x")
        self.time_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_scale_slider.setRange(1, 24)
        self.time_scale_slider.setValue(6)
        self.time_scale_slider.setFixedWidth(180)
        self.time_scale_slider.setToolTip("调整仿真内时间和现实时间的比例")
        self.path_checkbox = QCheckBox("显示路径")

        self.start_button.clicked.connect(self._open_config_dialog)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button.clicked.connect(self.stopRequested.emit)
        self.time_scale_slider.valueChanged.connect(self._time_scale_slider_changed)
        self.path_checkbox.toggled.connect(self.canvas.set_show_paths)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.start_button)
        top_bar.addWidget(self.pause_button)
        top_bar.addWidget(self.stop_button)
        top_bar.addSpacing(18)
        top_bar.addWidget(self.time_scale_label)
        top_bar.addWidget(self.time_scale_slider)
        top_bar.addWidget(self.path_checkbox)
        top_bar.addSpacing(18)
        top_bar.addWidget(self.status_label, 1)

        content = QHBoxLayout()
        content.setSpacing(0)
        content.addWidget(self.canvas, 1)
        content.addWidget(self.stats_panel)

        root = QVBoxLayout()
        root.addLayout(top_bar)
        root.addLayout(content, 1)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

    def _open_config_dialog(self) -> None:
        if self._running:
            return
        dialog = ConfigDialog(self)
        if dialog.exec():
            self.start_simulation(dialog.config())

    def start_simulation(self, config: SimulationConfig) -> None:
        config = replace(config, time_scale=float(self.time_scale_slider.value()))
        self._running = True
        self._paused = False
        self.start_button.setEnabled(False)
        self.pause_button.setText("暂停")
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.status_label.setText(
            f"准备启动：{config.sim_minutes} 分钟，{config.time_scale:g} 游戏秒/现实秒"
        )
        self.startRequested.emit(config)

    def _time_scale_slider_changed(self, value: int) -> None:
        self.time_scale_label.setText(f"时间倍率 {value}x")
        self.timeScaleChanged.emit(float(value))

    def _toggle_pause(self) -> None:
        if not self._running:
            return
        self._paused = not self._paused
        self.pause_button.setText("继续" if self._paused else "暂停")
        self.pauseChanged.emit(self._paused)

    @pyqtSlot(object)
    def update_frame(self, frame: dict) -> None:
        self.canvas.set_frame(frame)
        self.stats_panel.set_frame(frame)

    @pyqtSlot(str)
    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    @pyqtSlot(object)
    def simulation_finished(self, summary: RunSummary) -> None:
        self._running = False
        self._paused = False
        self.start_button.setEnabled(True)
        self.pause_button.setText("暂停")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.status_label.setText(
            f"{summary.status}：生成 {summary.spawned_students}，离场 {summary.served_students}，场内 {summary.active_students}"
        )

    @pyqtSlot(object)
    def show_error(self, error: object) -> None:
        self._running = False
        self._paused = False
        self.start_button.setEnabled(True)
        self.pause_button.setText("暂停")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        QMessageBox.critical(self, "仿真错误", str(error))
