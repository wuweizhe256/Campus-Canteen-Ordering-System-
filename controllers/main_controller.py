from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot

from models.entities import SimulationConfig
from models.simulation_worker import SimulationWorker
from views.main_window import MainWindow


class MainController(QObject):
    stopWorker = pyqtSignal()
    pauseWorker = pyqtSignal(bool)
    updateTimeScale = pyqtSignal(float)

    def __init__(self, window: MainWindow) -> None:
        super().__init__()
        self.window = window
        self.thread: QThread | None = None
        self.worker: SimulationWorker | None = None

        self.window.startRequested.connect(self.start_simulation)
        self.window.stopRequested.connect(self.stop_simulation)
        self.window.pauseChanged.connect(self.pause_simulation)
        self.window.timeScaleChanged.connect(self.change_time_scale)

    @pyqtSlot(object)
    def start_simulation(self, config: SimulationConfig) -> None:
        if self.thread is not None:
            return

        self.thread = QThread()
        self.worker = SimulationWorker(config)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.frameReady.connect(self.window.update_frame)
        self.worker.statusChanged.connect(self.window.set_status)
        self.worker.finished.connect(self.window.simulation_finished)
        self.worker.finished.connect(self._cleanup_thread)
        self.worker.errorOccurred.connect(self.window.show_error)
        self.worker.errorOccurred.connect(self._cleanup_thread)
        self.stopWorker.connect(self.worker.stop, Qt.ConnectionType.DirectConnection)
        self.pauseWorker.connect(self.worker.set_paused, Qt.ConnectionType.DirectConnection)
        self.updateTimeScale.connect(self.worker.set_time_scale, Qt.ConnectionType.DirectConnection)
        self.thread.finished.connect(self.worker.deleteLater)

        self.thread.start()

    @pyqtSlot()
    def stop_simulation(self) -> None:
        if self.worker is not None:
            self.window.set_status("正在停止...")
            self.stopWorker.emit()

    @pyqtSlot(bool)
    def pause_simulation(self, paused: bool) -> None:
        if self.worker is not None:
            self.pauseWorker.emit(paused)

    @pyqtSlot(float)
    def change_time_scale(self, time_scale: float) -> None:
        if self.worker is not None:
            self.updateTimeScale.emit(time_scale)

    def _cleanup_thread(self, *_args) -> None:
        try:
            self.stopWorker.disconnect()
        except TypeError:
            pass
        try:
            self.pauseWorker.disconnect()
        except TypeError:
            pass
        try:
            self.updateTimeScale.disconnect()
        except TypeError:
            pass
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(1500)
            self.thread.deleteLater()
        self.thread = None
        self.worker = None
