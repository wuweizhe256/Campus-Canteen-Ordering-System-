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
from utils.fonts import stylesheet_font_family
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
        self.resize(1480, 860)
        self._running = False
        self._paused = False

        self.canvas = CanvasWidget()
        self.stats_panel = StatsPanel()
        self.app_title = QLabel("校园食堂就餐仿真系统")
        self.app_title.setObjectName("AppTitle")
        self.app_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.start_button = QPushButton("开始仿真")
        self.start_button.setObjectName("PrimaryButton")
        self.pause_button = QPushButton("暂停")
        self.pause_button.setObjectName("SecondaryButton")
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.setEnabled(False)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("StatusBadge")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.time_scale_label = QLabel("时间倍率 6x")
        self.time_scale_label.setObjectName("ToolbarLabel")
        self.time_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_scale_slider.setRange(1, 24)
        self.time_scale_slider.setValue(6)
        self.time_scale_slider.setFixedWidth(180)
        self.time_scale_slider.setToolTip("调整仿真内时间和现实时间的比例")
        self.path_checkbox = QCheckBox("显示调试层")
        self.path_checkbox.setObjectName("PathToggle")
        self.zoom_label = QLabel("画布缩放 100%")
        self.zoom_label.setObjectName("ToolbarLabel")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(60, 180)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.setToolTip("调整左侧食堂演示画布缩放比例")
        self.reset_view_button = QPushButton("重置视图")
        self.reset_view_button.setObjectName("SecondaryButton")

        self.start_button.clicked.connect(self._open_config_dialog)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button.clicked.connect(self.stopRequested.emit)
        self.time_scale_slider.valueChanged.connect(self._time_scale_slider_changed)
        self.path_checkbox.toggled.connect(self.canvas.set_show_paths)
        self.zoom_slider.valueChanged.connect(self._zoom_slider_changed)
        self.canvas.zoomChanged.connect(self._canvas_zoom_changed)
        self.reset_view_button.clicked.connect(self.canvas.reset_view)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(18, 12, 18, 12)
        top_bar.setSpacing(12)
        top_bar.addWidget(self.app_title)
        top_bar.addSpacing(16)
        top_bar.addWidget(self.start_button)
        top_bar.addWidget(self.pause_button)
        top_bar.addWidget(self.stop_button)
        top_bar.addSpacing(18)
        top_bar.addWidget(self.time_scale_label)
        top_bar.addWidget(self.time_scale_slider)
        top_bar.addWidget(self.path_checkbox)
        top_bar.addWidget(self.zoom_label)
        top_bar.addWidget(self.zoom_slider)
        top_bar.addWidget(self.reset_view_button)
        top_bar.addSpacing(18)
        top_bar.addWidget(self.status_label, 1)

        toolbar = QWidget()
        toolbar.setObjectName("TopBar")
        toolbar.setLayout(top_bar)

        content = QHBoxLayout()
        content.setSpacing(0)
        content.setContentsMargins(0, 0, 0, 0)
        content.addWidget(self.canvas, 1)
        content.addWidget(self.stats_panel)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(toolbar)
        root.addLayout(content, 1)

        container = QWidget()
        container.setObjectName("Root")
        container.setLayout(root)
        self.setCentralWidget(container)
        self._apply_style()

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

    def _zoom_slider_changed(self, value: int) -> None:
        zoom = value / 100.0
        self.zoom_label.setText(f"画布缩放 {value}%")
        self.canvas.set_view_zoom(zoom)

    def _canvas_zoom_changed(self, zoom: float) -> None:
        value = int(round(zoom * 100))
        self.zoom_label.setText(f"画布缩放 {value}%")
        if self.zoom_slider.value() == value:
            return
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(value)
        self.zoom_slider.blockSignals(False)

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

    def _apply_style(self) -> None:
        font_family = stylesheet_font_family()
        style = """
            QWidget#Root {
                background: #e7efe2;
                font-family: "Microsoft YaHei UI";
            }
            QWidget#TopBar {
                background: #fff7ed;
                border-bottom: 1px solid #d6c2a8;
            }
            QLabel#AppTitle {
                color: #0f172a;
                font: 700 15pt "Microsoft YaHei UI";
                padding-right: 6px;
            }
            QLabel#ToolbarLabel {
                color: #334155;
                font: 700 10pt "Microsoft YaHei UI";
            }
            QLabel#StatusBadge {
                color: #0f172a;
                background: #eaf1f8;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
                padding: 5px 12px;
                font: 9pt "Microsoft YaHei UI";
            }
            QPushButton {
                border: 0;
                border-radius: 8px;
                padding: 8px 18px;
                min-width: 78px;
                font: 700 10pt "Microsoft YaHei UI";
            }
            QPushButton#PrimaryButton {
                color: #ffffff;
                background: #0f766e;
            }
            QPushButton#PrimaryButton:hover {
                background: #0d9488;
            }
            QPushButton#SecondaryButton {
                color: #0f172a;
                background: #e2e8f0;
            }
            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }
            QPushButton#DangerButton {
                color: #ffffff;
                background: #dc2626;
            }
            QPushButton#DangerButton:hover {
                background: #ef4444;
            }
            QPushButton:disabled {
                color: #94a3b8;
                background: #f1f5f9;
            }
            QCheckBox#PathToggle {
                color: #0f172a;
                font: 10pt "Microsoft YaHei UI";
                spacing: 8px;
            }
            QCheckBox#PathToggle::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid #94a3b8;
                background: #ffffff;
            }
            QCheckBox#PathToggle::indicator:checked {
                background: #0f766e;
                border: 1px solid #0f766e;
            }
            QSlider::groove:horizontal {
                height: 6px;
                border-radius: 3px;
                background: #cbd5e1;
            }
            QSlider::sub-page:horizontal {
                border-radius: 3px;
                background: #0f766e;
            }
            QSlider::handle:horizontal {
                width: 18px;
                height: 18px;
                margin: -7px 0;
                border-radius: 9px;
                background: #ffffff;
                border: 2px solid #0f766e;
            }
            """
        self.setStyleSheet(style.replace("Microsoft YaHei UI", font_family))
