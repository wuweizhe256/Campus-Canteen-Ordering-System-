from __future__ import annotations

import time

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from models.entities import SimulationConfig
from models.simulation_engine import SimulationEngine


class SimulationWorker(QObject):
    frameReady = pyqtSignal(object)
    statusChanged = pyqtSignal(str)
    finished = pyqtSignal(object)
    errorOccurred = pyqtSignal(object)
    _DETAIL_FRAME_INTERVAL_SECONDS = 0.5

    def __init__(self, config: SimulationConfig) -> None:
        super().__init__()
        self.engine = SimulationEngine(config)

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.engine.initialize()
            self.statusChanged.emit("运行中")
            last_real_time = time.perf_counter()
            last_detail_frame_time = 0.0

            while not self.engine._stop_requested and not self.engine.is_finished:
                now = time.perf_counter()
                if self.engine._paused:
                    last_real_time = now
                    QThread.msleep(40)
                    continue

                real_delta = now - last_real_time
                last_real_time = now
                include_details = now - last_detail_frame_time >= self._DETAIL_FRAME_INTERVAL_SECONDS
                frame = self.engine.step(
                    real_delta * self.engine.time_scale,
                    lightweight_students=True,
                    include_student_details=include_details,
                )
                if include_details:
                    last_detail_frame_time = now
                self.frameReady.emit(frame)
                QThread.msleep(16)

            status = "已停止" if self.engine._stop_requested else "已结束"
            self.statusChanged.emit(status)
            self.frameReady.emit(self.engine.build_frame(include_student_details=True))
            self.finished.emit(self.engine.summary(status))
        except Exception as exc:  # pragma: no cover - delivered to UI at runtime
            self.errorOccurred.emit(exc)

    @pyqtSlot()
    def stop(self) -> None:
        self.engine.stop()

    @pyqtSlot(bool)
    def set_paused(self, paused: bool) -> None:
        self.engine.set_paused(paused)
        self.statusChanged.emit("已暂停" if paused else "运行中")

    @pyqtSlot(float)
    def set_time_scale(self, time_scale: float) -> None:
        self.engine.set_time_scale(time_scale)
