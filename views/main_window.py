from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import QElapsedTimer, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from models.entities import RunSummary, SimulationConfig
from utils.fonts import set_ui_font_scale, stylesheet_font_family, ui_font
from views.canvas_widget import CanvasWidget
from views.config_dialog import ConfigDialog
from views.settings_dialog import SettingsDialog
from views.simulation_result_dialog import SimulationResultDialog
from views.stall_info_popup import StallInfoPopup
from views.stats_panel import StatsPanel
from views.student_info_popup import StudentInfoPopup
from views.table_info_popup import TableInfoPopup
from views.ui_widgets import PigSlider


class MainWindow(QMainWindow):
    startRequested = pyqtSignal(object)
    stopRequested = pyqtSignal()
    pauseChanged = pyqtSignal(bool)
    timeScaleChanged = pyqtSignal(float)
    _STATS_PANEL_UPDATE_INTERVAL_MS = 500
    _RESIZE_AFTER_RESTORE_DELAY_MS = 300
    _MAX_RESIZE_AFTER_RESTORE_ATTEMPTS = 8

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("校园食堂就餐仿真系统")
        self.resize(1600, 920)
        self._running = False
        self._paused = False
        self._font_point_size = 10
        self._font_scale = 1.0
        self.settings_dialog: SettingsDialog | None = None
        self._pending_window_settings: tuple[tuple[int, int] | None, int] | None = None
        self._settings_apply_scheduled = False
        self._deferred_resolution: tuple[int, int] | None = None
        self._deferred_resolution_attempts = 0
        self._toolbar_clusters: list[QFrame] = []
        self._stall_popup: StallInfoPopup | None = None
        self._table_popup: TableInfoPopup | None = None
        self._student_popup: StudentInfoPopup | None = None
        self._student_details_by_id: dict[int, dict] = {}
        self._last_frame: dict | None = None
        self._result_dialog: SimulationResultDialog | None = None
        self._stats_update_clock = QElapsedTimer()
        self._stats_update_clock.invalidate()

        self.canvas = CanvasWidget()
        self.stats_panel = StatsPanel()
        self.brand_block = QWidget()
        self.brand_block.setObjectName("BrandBlock")
        self.app_title = QLabel("校园食堂就餐仿真系统")
        self.app_title.setObjectName("AppTitle")
        self.app_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.app_subtitle = QLabel("实时排队 · 座位 · 出餐可视化")
        self.app_subtitle.setObjectName("AppSubtitle")

        self.start_button = QPushButton("开始仿真")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setMinimumSize(118, 42)
        self.pause_button = QPushButton("暂停")
        self.pause_button.setObjectName("SecondaryButton")
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.setEnabled(False)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("StatusBadge")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setMinimumWidth(180)
        self.time_scale_label = QLabel("时间倍率 6x")
        self.time_scale_label.setObjectName("ToolbarLabel")
        self.time_scale_slider = PigSlider(Qt.Orientation.Horizontal)
        self.time_scale_slider.setRange(1, 24)
        self.time_scale_slider.setValue(6)
        self.time_scale_slider.setFixedWidth(150)
        self.time_scale_slider.setToolTip("调整仿真内时间和现实时间的比例")
        self.path_checkbox = QCheckBox("显示调试层")
        self.path_checkbox.setObjectName("PathToggle")
        self.obstacle_checkbox = QCheckBox("障碍物层")
        self.obstacle_checkbox.setObjectName("PathToggle")
        self.zoom_label = QLabel("画布缩放 100%")
        self.zoom_label.setObjectName("ToolbarLabel")
        self.zoom_slider = PigSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(60, 180)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(112)
        self.zoom_slider.setToolTip("调整左侧食堂演示画布缩放比例")
        self.reset_view_button = QPushButton("重置视图")
        self.reset_view_button.setObjectName("SecondaryButton")
        self.settings_button = QPushButton("设置")
        self.settings_button.setObjectName("SecondaryButton")
        self.settings_button.setEnabled(False)

        self.start_button.clicked.connect(self._open_config_dialog)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button.clicked.connect(self._request_stop_simulation)
        self.time_scale_slider.valueChanged.connect(self._time_scale_slider_changed)
        self.path_checkbox.toggled.connect(self.canvas.set_show_paths)
        self.obstacle_checkbox.toggled.connect(self.canvas.set_show_obstacles)
        self.zoom_slider.valueChanged.connect(self._zoom_slider_changed)
        self.canvas.zoomChanged.connect(self._canvas_zoom_changed)
        self.canvas.stallClicked.connect(self._show_stall_popup)
        self.canvas.tableClicked.connect(self._show_table_popup)
        self.canvas.studentClicked.connect(self._show_student_popup)
        self.reset_view_button.clicked.connect(self.canvas.reset_view)
        self.settings_button.clicked.connect(self._open_settings_dialog)

        brand_layout = QVBoxLayout()
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(1)
        brand_layout.addWidget(self.app_title)
        brand_layout.addWidget(self.app_subtitle)
        self.brand_block.setLayout(brand_layout)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(18, 10, 18, 10)
        top_bar.setSpacing(12)
        top_bar.addWidget(self.brand_block)
        top_bar.addWidget(self._toolbar_cluster(self.start_button, self.pause_button, self.stop_button))
        top_bar.addWidget(self._toolbar_cluster(self.time_scale_label, self.time_scale_slider))
        top_bar.addWidget(self._toolbar_cluster(self.path_checkbox, self.obstacle_checkbox, self.zoom_label, self.zoom_slider, self.reset_view_button, self.settings_button))
        top_bar.addStretch(1)
        top_bar.addWidget(self.status_label)

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

    def _toolbar_cluster(self, *widgets: QWidget) -> QFrame:
        cluster = QFrame()
        cluster.setObjectName("ToolbarCluster")
        cluster.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        cluster.setMinimumHeight(64)
        layout = QHBoxLayout()
        layout.setContentsMargins(9, 6, 9, 6)
        layout.setSpacing(7)
        for widget in widgets:
            layout.addWidget(widget)
        cluster.setLayout(layout)
        self._toolbar_clusters.append(cluster)
        return cluster

    def _open_config_dialog(self) -> None:
        if self._running:
            return
        dialog = ConfigDialog(self, current_resolution=(self.width(), self.height()))
        if dialog.exec():
            resolution = dialog.selected_resolution()
            if resolution != (self.width(), self.height()):
                self._resize_window_safely(*resolution)
            self.start_simulation(dialog.config())

    def _open_settings_dialog(self) -> None:
        if not self._running:
            return
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(
                self,
                current_font_size=self._font_point_size,
            )
            self.settings_dialog.settingsApplied.connect(self._apply_window_settings)
            self.settings_dialog.finished.connect(self._settings_dialog_closed)

        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()
        self._position_settings_dialog()

    def _settings_dialog_closed(self, *_args) -> None:
        self.settings_dialog = None

    def _close_settings_dialog(self) -> None:
        if self.settings_dialog is None:
            return
        self.settings_dialog.close()
        self.settings_dialog = None

    def _show_stall_popup(self, stall: dict) -> None:
        if self._table_popup is not None:
            self._table_popup.close()
        if self._student_popup is not None:
            self._student_popup.close()
        if self._stall_popup is not None:
            self._stall_popup.close()
        self.canvas.set_selected_student(None)
        self._stall_popup = StallInfoPopup(stall, self)
        self._stall_popup.finished.connect(self._stall_popup_closed)
        # 定位到鼠标附近
        from PyQt6.QtGui import QCursor
        cursor_pos = QCursor.pos()
        self._stall_popup.move(
            cursor_pos.x() + 16,
            cursor_pos.y() + 16,
        )
        self._stall_popup.show()

    def _stall_popup_closed(self) -> None:
        self._stall_popup = None

    def _show_table_popup(self, table: dict) -> None:
        if self._stall_popup is not None:
            self._stall_popup.close()
        if self._student_popup is not None:
            self._student_popup.close()
        if self._table_popup is not None:
            self._table_popup.close()
        self.canvas.set_selected_student(None)
        self._table_popup = TableInfoPopup(table, self)
        self._table_popup.finished.connect(self._table_popup_closed)
        from PyQt6.QtGui import QCursor
        cursor_pos = QCursor.pos()
        self._table_popup.move(
            cursor_pos.x() + 16,
            cursor_pos.y() + 16,
        )
        self._table_popup.show()

    def _table_popup_closed(self) -> None:
        self._table_popup = None

    def _show_student_popup(self, student: dict) -> None:
        if self._stall_popup is not None:
            self._stall_popup.close()
        if self._table_popup is not None:
            self._table_popup.close()
        if self._student_popup is not None:
            self._student_popup.close()
        student_id = student.get("id")
        selected_id = int(student_id) if isinstance(student_id, (int, float)) else None
        self.canvas.set_selected_student(selected_id)
        self._student_popup = StudentInfoPopup(self._student_detail_or_render(student), self)
        self._student_popup.finished.connect(self._student_popup_closed)
        from PyQt6.QtGui import QCursor
        cursor_pos = QCursor.pos()
        self._student_popup.move(
            cursor_pos.x() + 16,
            cursor_pos.y() + 16,
        )
        self._student_popup.show()

    def _student_popup_closed(self) -> None:
        self._student_popup = None
        self.canvas.set_selected_student(None)

    def _result_dialog_closed(self) -> None:
        self._result_dialog = None

    @pyqtSlot(object, int)
    def _apply_window_settings(self, resolution: tuple[int, int] | None, font_size: int) -> None:
        if not self._running:
            return
        self._pending_window_settings = (resolution, font_size)
        if self._settings_apply_scheduled:
            return
        self._settings_apply_scheduled = True
        QTimer.singleShot(0, self._flush_window_settings)

    def _flush_window_settings(self) -> None:
        self._settings_apply_scheduled = False
        pending = self._pending_window_settings
        self._pending_window_settings = None
        if pending is None or not self._running:
            return
        resolution, font_size = pending
        if resolution is not None:
            width, height = resolution
            self._resize_window_safely(width, height)

        self._font_point_size = font_size
        self._font_scale = font_size / 10.0
        set_ui_font_scale(self._font_scale)
        app = QApplication.instance()
        if app is not None:
            app.setFont(ui_font(10))
        self._apply_style()
        self.stats_panel.apply_font_scale(self._font_scale)
        self.canvas.update()
        if resolution is None:
            self.status_label.setText(f"设置已应用：字体 {font_size} pt")
        else:
            self.status_label.setText(f"设置已应用：{width} x {height}，字体 {font_size} pt")
        self._position_settings_dialog()

    def _resize_window_safely(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            return
        if self.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen):
            self._deferred_resolution = (width, height)
            self._deferred_resolution_attempts = 0
            self.showNormal()
            QTimer.singleShot(self._RESIZE_AFTER_RESTORE_DELAY_MS, self._apply_deferred_resolution)
            return
        self._deferred_resolution = None
        self.resize(width, height)

    def _apply_deferred_resolution(self) -> None:
        resolution = self._deferred_resolution
        if resolution is None or not self._running:
            return
        width, height = resolution
        if self.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen):
            self._deferred_resolution_attempts += 1
            if self._deferred_resolution_attempts >= self._MAX_RESIZE_AFTER_RESTORE_ATTEMPTS:
                self._deferred_resolution = None
                self._deferred_resolution_attempts = 0
                self.status_label.setText("分辨率未应用：请先退出最大化窗口")
                return
            QTimer.singleShot(self._RESIZE_AFTER_RESTORE_DELAY_MS, self._apply_deferred_resolution)
            return
        self._deferred_resolution = None
        self._deferred_resolution_attempts = 0
        self.resize(width, height)
        self._position_settings_dialog()

    def _position_settings_dialog(self) -> None:
        if self.settings_dialog is None:
            return
        anchor = self.settings_button.mapToGlobal(self.settings_button.rect().bottomRight())
        self.settings_dialog.move(
            anchor.x() - self.settings_dialog.width(),
            anchor.y() + 8,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._position_settings_dialog()

    def moveEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().moveEvent(event)
        self._position_settings_dialog()

    def _request_stop_simulation(self) -> None:
        if not self._running:
            return
        self.settings_button.setEnabled(False)
        self._close_settings_dialog()
        self.stopRequested.emit()

    def start_simulation(self, config: SimulationConfig) -> None:
        config = replace(config, time_scale=float(self.time_scale_slider.value()))
        self.path_checkbox.setChecked(config.show_path_debug_layer)
        self.obstacle_checkbox.setChecked(config.show_obstacle_layer)
        self._stats_update_clock.invalidate()
        self._student_details_by_id.clear()
        self._running = True
        self._paused = False
        self.start_button.setEnabled(False)
        self.pause_button.setText("暂停")
        self.pause_button.setObjectName("SecondaryButton")
        self.pause_button.style().unpolish(self.pause_button)
        self.pause_button.style().polish(self.pause_button)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.settings_button.setEnabled(True)
        self.status_label.setText(
            f"准备启动：{config.sim_minutes} 分钟，{config.time_scale:g} 游戏秒/现实秒"
        )
        self.startRequested.emit(config)

    def _time_scale_slider_changed(self, value: int) -> None:
        self.time_scale_label.setText(f"时间倍率 {value}x")
        self._sync_toolbar_metrics()
        self.timeScaleChanged.emit(float(value))

    def _zoom_slider_changed(self, value: int) -> None:
        zoom = value / 100.0
        self.zoom_label.setText(f"画布缩放 {value}%")
        self._sync_toolbar_metrics()
        self.canvas.set_view_zoom(zoom)

    def _canvas_zoom_changed(self, zoom: float) -> None:
        value = int(round(zoom * 100))
        self.zoom_label.setText(f"画布缩放 {value}%")
        self._sync_toolbar_metrics()
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
        self.pause_button.setObjectName("PauseActiveButton" if self._paused else "SecondaryButton")
        self.pause_button.style().unpolish(self.pause_button)
        self.pause_button.style().polish(self.pause_button)
        self.pauseChanged.emit(self._paused)

    @pyqtSlot(object)
    def update_frame(self, frame: dict) -> None:
        self._last_frame = frame
        self._update_student_details_cache(frame)
        self.canvas.set_frame(frame)
        if self._should_update_stats_panel():
            self.stats_panel.set_frame(frame)
        self._refresh_stall_popup(frame)
        self._refresh_table_popup(frame)
        self._refresh_student_popup(frame)

    def _should_update_stats_panel(self) -> bool:
        if not self._running:
            return True
        if not self._stats_update_clock.isValid():
            self._stats_update_clock.start()
            return True
        if self._stats_update_clock.elapsed() < self._STATS_PANEL_UPDATE_INTERVAL_MS:
            return False
        self._stats_update_clock.restart()
        return True

    def _refresh_stall_popup(self, frame: dict) -> None:
        if self._stall_popup is None:
            return
        popup_id = self._stall_popup.stall_id()
        for stall in frame.get("stalls", []):
            if isinstance(stall, dict) and stall.get("id") == popup_id:
                self._stall_popup.update_stall(stall)
                return

    def _refresh_table_popup(self, frame: dict) -> None:
        if self._table_popup is None:
            return
        popup_id = self._table_popup.table_id()
        for table in frame.get("tables", []):
            if isinstance(table, dict) and table.get("id") == popup_id:
                self._table_popup.update_table(table)
                return

    def _refresh_student_popup(self, frame: dict) -> None:
        if self._student_popup is None:
            return
        popup_id = self._student_popup.student_id()
        active_student = None
        for student in frame.get("students", []):
            if isinstance(student, dict) and student.get("id") == popup_id:
                active_student = student
                break
        if active_student is None:
            self._student_details_by_id.pop(popup_id, None)
            self._student_popup.update_student(None)
            self.canvas.set_selected_student(None)
            return
        self._student_popup.update_student(self._student_detail_or_render(active_student))
        self.canvas.set_selected_student(popup_id)

    def _update_student_details_cache(self, frame: dict) -> None:
        details = frame.get("student_details")
        if isinstance(details, list):
            for student in details:
                if not isinstance(student, dict):
                    continue
                student_id = student.get("id")
                if isinstance(student_id, (int, float)):
                    self._student_details_by_id[int(student_id)] = student

        active_ids = {
            int(student.get("id"))
            for student in frame.get("students", [])
            if isinstance(student, dict) and isinstance(student.get("id"), (int, float))
        }
        stale_ids = set(self._student_details_by_id) - active_ids
        for student_id in stale_ids:
            self._student_details_by_id.pop(student_id, None)

    def _student_detail_or_render(self, student: dict) -> dict:
        student_id = student.get("id")
        if not isinstance(student_id, (int, float)):
            return student
        detail = self._student_details_by_id.get(int(student_id))
        if detail is None:
            return student
        merged = dict(detail)
        merged.update(student)
        return merged

    @pyqtSlot(str)
    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    @pyqtSlot(object)
    def simulation_finished(self, summary: RunSummary) -> None:
        self._running = False
        self._paused = False
        self._stats_update_clock.invalidate()
        self._pending_window_settings = None
        self._deferred_resolution = None
        self._close_settings_dialog()
        self.start_button.setEnabled(True)
        self.pause_button.setText("暂停")
        self.pause_button.setObjectName("SecondaryButton")
        self.pause_button.style().unpolish(self.pause_button)
        self.pause_button.style().polish(self.pause_button)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.status_label.setText(
            f"{summary.status}：生成 {summary.spawned_students}，离场 {summary.served_students}，场内 {summary.active_students}"
        )

        # 弹出仿真结果大窗口
        if self._last_frame is not None:
            self._result_dialog = SimulationResultDialog(
                self._last_frame, summary, self,
            )
            self._result_dialog.finished.connect(self._result_dialog_closed)
            self._result_dialog.show()

    @pyqtSlot(object)
    def show_error(self, error: object) -> None:
        self._running = False
        self._paused = False
        self._pending_window_settings = None
        self._deferred_resolution = None
        self._close_settings_dialog()
        self.start_button.setEnabled(True)
        self.pause_button.setText("暂停")
        self.pause_button.setObjectName("SecondaryButton")
        self.pause_button.style().unpolish(self.pause_button)
        self.pause_button.style().polish(self.pause_button)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        QMessageBox.critical(self, "仿真错误", str(error))

    def _sync_toolbar_metrics(self) -> None:
        self.time_scale_label.setMinimumWidth(
            self.time_scale_label.fontMetrics().horizontalAdvance("时间倍率 24x") + 12
        )
        self.zoom_label.setMinimumWidth(
            self.zoom_label.fontMetrics().horizontalAdvance("画布缩放 180%") + 12
        )
        self.reset_view_button.setMinimumWidth(
            self.reset_view_button.fontMetrics().horizontalAdvance("重置视图") + 32
        )
        self.settings_button.setMinimumWidth(
            self.settings_button.fontMetrics().horizontalAdvance("设置") + 32
        )
        cluster_height = max(64, round(64 * self._font_scale))
        for cluster in self._toolbar_clusters:
            cluster.setMinimumHeight(cluster_height)

    def _apply_style(self) -> None:
        font_family = stylesheet_font_family()
        title_size = max(11, round(15 * self._font_scale))
        toolbar_size = max(8, round(10 * self._font_scale))
        status_size = max(8, round(9 * self._font_scale))
        style = """
            QWidget#Root {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #e7efe2, stop:0.55 #f7efe2, stop:1 #f0e4d3);
                font-family: "Microsoft YaHei UI";
            }
            QWidget#TopBar {
                background: rgba(255, 250, 240, 242);
                border-bottom: 1px solid #dccdb8;
            }
            QWidget#BrandBlock {
                background: transparent;
            }
            QLabel#AppTitle {
                color: #17211f;
                font: 800 __TITLE_SIZE__pt "Microsoft YaHei UI";
                padding: 0;
            }
            QLabel#AppSubtitle {
                color: #64736e;
                font: 9pt "Microsoft YaHei UI";
            }
            QLabel#ToolbarLabel {
                color: #33423f;
                font: 700 __TOOLBAR_SIZE__pt "Microsoft YaHei UI";
            }
            QLabel#StatusBadge {
                color: #0f5f59;
                background: #dff4ef;
                border: 1px solid #9ccfc6;
                border-radius: 14px;
                padding: 6px 13px;
                font: 700 __STATUS_SIZE__pt "Microsoft YaHei UI";
            }
            QFrame#ToolbarCluster {
                background: rgba(255, 255, 255, 155);
                border: 1px solid rgba(220, 205, 184, 170);
                border-radius: 16px;
            }
            QPushButton {
                border: 1px solid transparent;
                border-radius: 12px;
                padding: 7px 12px;
                min-width: 58px;
                font: 800 __TOOLBAR_SIZE__pt "Microsoft YaHei UI";
            }
            QPushButton#PrimaryButton {
                color: #ffffff;
                background: #0f766e;
                border-color: #0f5f59;
            }
            QPushButton#PrimaryButton:hover {
                background: #13887f;
            }
            QPushButton#PrimaryButton:pressed {
                background: #0f5f59;
                padding-top: 9px;
                padding-bottom: 7px;
            }
            QPushButton#SecondaryButton {
                color: #17211f;
                background: #fffaf0;
                border-color: #dccdb8;
            }
            QPushButton#SecondaryButton:hover {
                background: #fff1d8;
                border-color: #d8842b;
            }
            QPushButton#SecondaryButton:pressed {
                background: #f7e1bd;
                padding-top: 9px;
                padding-bottom: 7px;
            }
            QPushButton#SecondaryButton:disabled {
                color: #9aa6a0;
                background: #edf1ec;
                border-color: #d8ded8;
            }
            QPushButton#PauseActiveButton {
                color: #7a3a00;
                background: #fff1d8;
                border-color: #d8842b;
            }
            QPushButton#DangerButton {
                color: #ffffff;
                background: #dc4a4a;
                border-color: #b93232;
            }
            QPushButton#DangerButton:hover {
                background: #e45d5d;
            }
            QPushButton#DangerButton:pressed {
                background: #b93232;
                padding-top: 9px;
                padding-bottom: 7px;
            }
            QPushButton:disabled {
                color: #9aa6a0;
                background: #edf1ec;
                border-color: #d8ded8;
            }
            QCheckBox#PathToggle {
                color: #273633;
                font: 700 9pt "Microsoft YaHei UI";
                spacing: 8px;
            }
            QCheckBox#PathToggle::indicator {
                width: 19px;
                height: 19px;
                border-radius: 7px;
                border: 1px solid #b8c8bd;
                background: #fffaf0;
            }
            QCheckBox#PathToggle::indicator:hover {
                border-color: #0f766e;
            }
            QCheckBox#PathToggle::indicator:checked {
                background: #0f766e;
                border: 1px solid #0f5f59;
            }
            QSlider::groove:horizontal {
                height: 10px;
                border-radius: 5px;
                background: #efe3d3;
            }
            QSlider::sub-page:horizontal {
                border-radius: 5px;
                background: #0f766e;
            }
            QSlider::add-page:horizontal {
                border-radius: 5px;
                background: #efe3d3;
            }
            QSlider::handle:horizontal {
                width: 36px;
                height: 36px;
                margin: -13px 0;
                border: 0;
                background: transparent;
            }
            QToolTip {
                color: #17211f;
                background: #fffaf0;
                border: 1px solid #dccdb8;
                border-radius: 8px;
                padding: 6px;
            }
            """
        self.setStyleSheet(
            style.replace("__TITLE_SIZE__", str(title_size))
            .replace("__TOOLBAR_SIZE__", str(toolbar_size))
            .replace("__STATUS_SIZE__", str(status_size))
            .replace("Microsoft YaHei UI", font_family)
        )
        self._sync_toolbar_metrics()
