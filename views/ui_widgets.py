from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSlider, QStyle, QStyleOptionSlider

from utils.fonts import stylesheet_font_family


class UiColors:
    INK = "#17211f"
    MUTED = "#64736e"
    PAPER = "#fffaf0"
    PAPER_2 = "#f7efe2"
    SAGE = "#e7efe2"
    SAGE_2 = "#d9e7d8"
    TEAL = "#0f766e"
    TEAL_DARK = "#0f5f59"
    TEAL_SOFT = "#dff4ef"
    AMBER = "#d8842b"
    AMBER_SOFT = "#fff1d8"
    PINK = "#f4a9bb"
    PINK_LIGHT = "#ffd6df"
    PIG_BLUSH = "#F3B7C5"
    ROSE = "#d9506f"
    DANGER = "#dc4a4a"
    BORDER = "#dccdb8"
    CARD = "#ffffff"


def app_stylesheet() -> str:
    font = stylesheet_font_family()
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
            font: 800 15pt "Microsoft YaHei UI";
            padding: 0;
        }
        QLabel#AppSubtitle {
            color: #64736e;
            font: 9pt "Microsoft YaHei UI";
        }
        QLabel#ToolbarLabel {
            color: #33423f;
            font: 700 9pt "Microsoft YaHei UI";
        }
        QLabel#StatusBadge {
            color: #0f5f59;
            background: #dff4ef;
            border: 1px solid #9ccfc6;
            border-radius: 14px;
            padding: 6px 13px;
            font: 700 9pt "Microsoft YaHei UI";
        }
        QWidget#ToolbarCluster {
            background: rgba(255, 255, 255, 155);
            border: 1px solid rgba(220, 205, 184, 170);
            border-radius: 16px;
        }
        QPushButton {
            border: 1px solid transparent;
            border-radius: 12px;
            padding: 8px 17px;
            min-width: 74px;
            font: 800 10pt "Microsoft YaHei UI";
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
    return style.replace("Microsoft YaHei UI", font)


def dialog_stylesheet() -> str:
    font = stylesheet_font_family()
    style = """
        QDialog {
            background: #f7f0e6;
            font-family: "Microsoft YaHei UI";
        }
        QScrollArea {
            background: transparent;
            border: 0;
        }
        QScrollArea > QWidget > QWidget {
            background: transparent;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 4px 2px 4px 2px;
        }
        QScrollBar::handle:vertical {
            background: #c9bca8;
            border-radius: 5px;
            min-height: 36px;
        }
        QScrollBar::handle:vertical:hover {
            background: #0f766e;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0;
        }
        QFrame#ConfigCard {
            color: #17211f;
            background: #fffaf3;
            border: 1px solid #e2d2be;
            border-radius: 15px;
        }
        QLabel#ConfigCardTitle {
            color: #0f5f59;
            font: 900 11pt "Microsoft YaHei UI";
            padding: 0 0 2px 0;
        }
        QLabel {
            color: #263633;
            font: 9pt "Microsoft YaHei UI";
        }
        QSpinBox {
            color: #17211f;
            background: #fffefa;
            border: 1px solid #d8c9b6;
            border-radius: 10px;
            padding: 4px 12px;
            min-width: 118px;
            min-height: 30px;
            font: 10pt "Microsoft YaHei UI";
        }
        QSpinBox:hover {
            border-color: #d8842b;
            background: #ffffff;
        }
        QSpinBox:focus {
            border: 1px solid #0f766e;
            background: #ffffff;
            selection-background-color: #dff4ef;
            selection-color: #17211f;
        }
        QSpinBox:disabled {
            color: #7d8b85;
            background: #e9efea;
            border-color: #cfdad2;
        }
        QSpinBox#CompactSpinBox {
            min-width: 70px;
            padding-left: 8px;
            padding-right: 8px;
        }
        QCheckBox {
            color: #273633;
            font: 9pt "Microsoft YaHei UI";
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 19px;
            height: 19px;
            border-radius: 7px;
            border: 1px solid #b8c8bd;
            background: #ffffff;
        }
        QCheckBox::indicator:checked {
            background: #0f766e;
            border-color: #0f5f59;
        }
        QPushButton {
            border: 1px solid #dccdb8;
            border-radius: 12px;
            padding: 8px 20px;
            min-width: 108px;
            min-height: 24px;
            font: 800 10pt "Microsoft YaHei UI";
            color: #17211f;
            background: #fffaf0;
        }
        QPushButton:hover {
            background: #fff1d8;
            border-color: #d8842b;
            margin-top: -1px;
            margin-bottom: 1px;
        }
        QPushButton:pressed {
            background: #f7e1bd;
            margin-top: 1px;
            margin-bottom: -1px;
        }
        QPushButton#DialogAcceptButton {
            color: #ffffff;
            background: #0f766e;
            border-color: #0f5f59;
        }
        QPushButton#DialogAcceptButton:hover {
            background: #13887f;
            border-color: #0f5f59;
        }
        QPushButton#DialogAcceptButton:pressed {
            background: #0f5f59;
        }
        """
    return style.replace("Microsoft YaHei UI", font)


def _adj(color: QColor, delta: int) -> QColor:
    return QColor(
        max(0, min(255, color.red() + delta)),
        max(0, min(255, color.green() + delta)),
        max(0, min(255, color.blue() + delta)),
        color.alpha(),
    )


def draw_pig_head(
    painter: QPainter,
    cx: float,
    cy: float,
    scale: float = 1.0,
    *,
    fill: str | QColor = "#F4A8BB",
    expr: str = "smile",
    badge: str | None = None,
    badge_color: str = "#0F8074",
    chef: bool = False,
    pressed: bool = False,
    facing: float = 0.0,
) -> None:
    if isinstance(fill, str):
        fill = QColor(fill)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(36, 48, 41, int((0.30 if pressed else 0.15) * 255)))
    painter.drawEllipse(QPointF(cx, cy + 22 * scale), 18 * scale, 6 * scale)

    head_y = cy - (1.6 * scale if pressed else 0.0)

    def draw_ear(ex: float, sign: int) -> None:
        painter.save()
        painter.translate(ex, head_y - 12 * scale)
        rotation = sign * (-0.18) - (sign * 0.08 if pressed else 0.0)
        painter.rotate(math.degrees(rotation))

        outer = QPainterPath()
        outer.moveTo(-5 * scale, 5 * scale)
        outer.quadTo(-2 * scale, -9 * scale, 7 * scale, -2 * scale)
        outer.quadTo(3 * scale, 6 * scale, -5 * scale, 5 * scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_adj(fill, -14))
        painter.drawPath(outer)

        inner = QPainterPath()
        inner.moveTo(-1 * scale, 3 * scale)
        inner.quadTo(0, -3 * scale, 4 * scale, 0)
        inner.quadTo(2 * scale, 4 * scale, -1 * scale, 3 * scale)
        painter.setBrush(QColor("#F8CDD7"))
        painter.drawPath(inner)
        painter.restore()

    draw_ear(cx - 10 * scale, 1)
    draw_ear(cx + 10 * scale, -1)

    gradient = QLinearGradient(cx, head_y - 15 * scale, cx, head_y + 15 * scale)
    gradient.setColorAt(0.0, _adj(fill, -4 if pressed else 12))
    gradient.setColorAt(1.0, _adj(fill, -18 if pressed else -6))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor("#BE4D6E"), 1.3 * scale))
    painter.drawEllipse(QPointF(cx, head_y), 15 * scale, 13.5 * scale)

    painter.save()
    painter.translate(cx - 5 * scale, head_y - 7 * scale)
    painter.rotate(math.degrees(-0.5))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 82))
    painter.drawEllipse(QPointF(0, 0), 5 * scale, 3 * scale)
    painter.restore()

    blush = QColor(UiColors.PIG_BLUSH)
    blush.setAlpha(50)
    painter.setBrush(blush)
    painter.drawEllipse(QPointF(cx - 9 * scale, head_y + 3 * scale), 2.6 * scale, 1.7 * scale)
    painter.drawEllipse(QPointF(cx + 9 * scale, head_y + 3 * scale), 2.6 * scale, 1.7 * scale)

    if chef:
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#CBB9A0"), 1 * scale))
        painter.drawRoundedRect(
            QRectF(cx - 11 * scale, head_y - 16 * scale, 22 * scale, 6 * scale),
            3 * scale,
            3 * scale,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        for dx, dy, radius in [(-7, -19, 4.4), (0, -21, 5.0), (7, -19, 4.4)]:
            painter.drawEllipse(QPointF(cx + dx * scale, head_y + dy * scale), radius * scale, radius * scale)

    painter.setBrush(QColor("#F4A6C0" if pressed else "#F8CDD7"))
    painter.setPen(QPen(QColor("#E1809B"), 1 * scale))
    painter.drawEllipse(QPointF(cx, head_y + 5 * scale), 8 * scale, 5.4 * scale)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#A83258" if pressed else "#C75D7E"))
    painter.drawEllipse(QPointF(cx - 2.6 * scale, head_y + 5 * scale), 1.2 * scale, 1.8 * scale)
    painter.drawEllipse(QPointF(cx + 2.6 * scale, head_y + 5 * scale), 1.2 * scale, 1.8 * scale)
    if pressed:
        painter.setBrush(QColor(255, 255, 255, 166))
        painter.drawEllipse(QPointF(cx - 1 * scale, head_y + 3.2 * scale), 2.6 * scale, 1.3 * scale)

    eye_offset = facing * 1.4 * scale
    painter.setBrush(QColor("#3A2230"))
    painter.drawEllipse(QPointF(cx - 6 * scale + eye_offset, head_y - 2 * scale), 1.9 * scale, 1.9 * scale)
    painter.drawEllipse(QPointF(cx + 6 * scale + eye_offset, head_y - 2 * scale), 1.9 * scale, 1.9 * scale)
    painter.setBrush(QColor("#ffffff"))
    painter.drawEllipse(QPointF(cx - 6.6 * scale + eye_offset, head_y - 2.6 * scale), 0.7 * scale, 0.7 * scale)
    painter.drawEllipse(QPointF(cx + 5.4 * scale + eye_offset, head_y - 2.6 * scale), 0.7 * scale, 0.7 * scale)

    mouth_y = head_y + 10.5 * scale
    if expr == "eat":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#8A1733"))
        painter.drawEllipse(QPointF(cx, mouth_y), 2.4 * scale, 2.0 * scale)
    elif expr == "flat":
        painter.setPen(QPen(QColor("#9F1239"), 1.2 * scale))
        painter.drawLine(QPointF(cx - 3 * scale, mouth_y), QPointF(cx + 3 * scale, mouth_y))
    else:
        painter.setPen(QPen(QColor("#9F1239"), 1.2 * scale))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - 3 * scale, mouth_y - 1 * scale)
        path.quadTo(cx, mouth_y + 3 * scale, cx + 3 * scale, mouth_y - 1 * scale)
        painter.drawPath(path)

    if badge:
        badge_width = (16 if len(badge) > 1 else 12) * scale
        badge_height = 12 * scale
        badge_x = cx + 12 * scale
        badge_y = cy - 12 * scale
        painter.setBrush(QColor(badge_color))
        painter.setPen(QPen(QColor("#ffffff"), 1.2 * scale))
        painter.drawRoundedRect(
            QRectF(badge_x - badge_width / 2, badge_y - badge_height / 2, badge_width, badge_height),
            5 * scale,
            5 * scale,
        )
        painter.setPen(QColor("#ffffff"))
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(int(8 * scale))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(badge_x - badge_width / 2, badge_y - badge_height / 2, badge_width, badge_height),
            Qt.AlignmentFlag.AlignCenter,
            badge,
        )


class PigSlider(QSlider):
    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.setFixedHeight(48)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        hint = super().sizeHint()
        return QSize(hint.width(), 48)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        hint = super().minimumSizeHint()
        return QSize(hint.width(), 48)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        if self.orientation() != Qt.Orientation.Horizontal:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        handle = self._handle_rect()
        pressed = self.isSliderDown()
        hovered = handle.contains(self.mapFromGlobal(QCursor.pos()))
        self._draw_pig_handle(painter, QRectF(handle), pressed, hovered)

    def _handle_rect(self) -> QRect:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
        center = rect.center()
        size = 36
        return QRect(center.x() - size // 2, center.y() - size // 2, size, size)

    def _draw_pig_handle(
        self,
        painter: QPainter,
        rect: QRectF,
        pressed: bool,
        hovered: bool,
    ) -> None:
        center = rect.center()
        draw_pig_head(
            painter,
            center.x(),
            center.y() + 1,
            0.96,
            fill="#F2A8BB" if not hovered else "#F4A8BB",
            expr="smile",
            pressed=pressed,
        )
