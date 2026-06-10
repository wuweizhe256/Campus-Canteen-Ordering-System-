from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from utils.fonts import ui_font


class StallInfoPopup(QDialog):
    """点击食堂窗口时弹出的档口信息面板，支持仿真帧实时刷新。"""

    def __init__(self, stall: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stall = stall
        self._stall_id: int = int(stall.get("id", 0))
        self._status_label: QLabel | None = None
        self._info_labels: dict[str, QLabel] = {}
        self._dishes_scroll: QScrollArea | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def stall_id(self) -> int:
        return self._stall_id

    def update_stall(self, stall: dict) -> None:
        """由外部调用，用最新的 stall 帧数据刷新弹窗内容。"""
        self._stall = stall
        self._refresh_status()
        self._refresh_info()
        self._refresh_dishes()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        stall_id = int(self._stall.get("id", 0))
        self.setWindowTitle(f"窗口 {stall_id + 1} 详情")
        self.setMinimumSize(360, 420)
        self.resize(400, 520)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Dialog)

        root = QVBoxLayout()
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # ---- 标题与状态 ----
        header = QHBoxLayout()
        header.setSpacing(12)
        title = QLabel(f"窗口 {stall_id + 1}")
        title.setFont(ui_font(15, QFont.Weight.Bold))
        title.setStyleSheet("color: #4a3728;")
        header.addWidget(title)
        header.addStretch()
        self._status_label = self._build_status_label()
        header.addWidget(self._status_label)
        root.addLayout(header)

        # ---- 分割线 ----
        root.addWidget(self._divider())

        # ---- 基本信息区块 ----
        root.addWidget(self._section_title("基本信息"))
        info_grid = self._info_grid()
        root.addLayout(info_grid)

        # ---- 分割线 ----
        root.addWidget(self._divider())

        # ---- 菜品列表区块 ----
        root.addWidget(self._section_title("菜品列表"))
        root.addWidget(self._build_dishes_scroll(), 1)

        self.setLayout(root)

    # ------------------------------------------------------------------
    # 区块组件
    # ------------------------------------------------------------------

    def _build_status_label(self) -> QLabel:
        status = self._stall.get("status", "open")
        label_map = {
            "pending": ("待营业", "#92400e", "#fef3c7"),
            "open": ("营业中", "#166534", "#dcfce7"),
            "sold_out": ("已售罄", "#991b1b", "#fee2e2"),
        }
        text, fg, bg = label_map.get(status, ("未知", "#475569", "#f1f5f9"))
        label = QLabel(text)
        label.setFont(ui_font(11, QFont.Weight.Bold))
        label.setFixedHeight(28)
        label.setMinimumWidth(64)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"QLabel {{ color: {fg}; background: {bg}; border-radius: 8px; padding: 2px 14px; }}"
        )
        return label

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(ui_font(11, QFont.Weight.Bold))
        label.setStyleSheet("color: #5c4a3a;")
        return label

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #d2dfc9;")
        return line

    # ------------------------------------------------------------------
    # 基本信息
    # ------------------------------------------------------------------

    def _info_grid(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(24)

        cook_time = self._stall.get("cook_time", 30.0)
        dishes = self._stall_dishes()
        total = len(dishes)
        available = sum(1 for d in dishes if d.get("available", False))

        left = QVBoxLayout()
        left.setSpacing(6)
        self._info_labels["cook_time"] = self._info_value_label(f"{cook_time:.1f} 秒")
        left.addWidget(self._info_row_widget("平均烹饪", self._info_labels["cook_time"]))
        layout.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(6)
        self._info_labels["total"] = self._info_value_label(str(total))
        right.addWidget(self._info_row_widget("菜品总数", self._info_labels["total"]))
        self._info_labels["available"] = self._info_value_label(f"{available} / {total}")
        right.addWidget(self._info_row_widget("在售菜品", self._info_labels["available"]))
        layout.addLayout(right)
        layout.addStretch()
        return layout

    @staticmethod
    def _info_value_label(text: str) -> QLabel:
        val = QLabel(text)
        val.setFont(ui_font(10, QFont.Weight.Bold))
        val.setStyleSheet("color: #44403c;")
        return val

    @staticmethod
    def _info_row_widget(label: str, value_widget: QLabel) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFont(ui_font(10))
        lbl.setStyleSheet("color: #78716c;")
        layout.addWidget(lbl)
        layout.addWidget(value_widget)
        layout.addStretch()
        row.setLayout(layout)
        return row

    # ------------------------------------------------------------------
    # 实时刷新
    # ------------------------------------------------------------------

    def _refresh_status(self) -> None:
        if self._status_label is None:
            return
        status = self._stall.get("status", "open")
        label_map = {
            "pending": ("待营业", "#92400e", "#fef3c7"),
            "open": ("营业中", "#166534", "#dcfce7"),
            "sold_out": ("已售罄", "#991b1b", "#fee2e2"),
        }
        text, fg, bg = label_map.get(status, ("未知", "#475569", "#f1f5f9"))
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"QLabel {{ color: {fg}; background: {bg}; border-radius: 8px; padding: 2px 14px; }}"
        )

    def _refresh_info(self) -> None:
        cook_time = self._stall.get("cook_time", 30.0)
        dishes = self._stall_dishes()
        total = len(dishes)
        available = sum(1 for d in dishes if d.get("available", False))
        if "cook_time" in self._info_labels:
            self._info_labels["cook_time"].setText(f"{cook_time:.1f} 秒")
        if "total" in self._info_labels:
            self._info_labels["total"].setText(str(total))
        if "available" in self._info_labels:
            self._info_labels["available"].setText(f"{available} / {total}")

    def _refresh_dishes(self) -> None:
        if self._dishes_scroll is None:
            return
        self._dishes_scroll.setWidget(self._dishes_content())

    # ------------------------------------------------------------------
    # 菜品列表
    # ------------------------------------------------------------------

    def _stall_dishes(self) -> list[dict]:
        raw = self._stall.get("dishes")
        if isinstance(raw, list):
            return [d for d in raw if isinstance(d, dict)]
        return []

    def _dishes_content(self) -> QWidget:
        """构建菜品列表内容 widget（不含滚动区域），供初始化和刷新复用。"""
        dishes = self._stall_dishes()

        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if not dishes:
            empty = QLabel("暂无菜品")
            empty.setFont(ui_font(10))
            empty.setStyleSheet("color: #9ca3af; padding: 24px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty)
            layout.addStretch()
            container.setLayout(layout)
            return container

        for dish in dishes:
            card = self._dish_card(dish)
            layout.addWidget(card)
        layout.addStretch()
        container.setLayout(layout)
        return container

    def _build_dishes_scroll(self) -> QScrollArea:
        """首次创建包裹菜品列表的滚动区域。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll.setWidget(self._dishes_content())
        self._dishes_scroll = scroll
        return scroll

    def _dish_card(self, dish: dict) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            "QWidget#DishCard { background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px; }"
        )
        card.setObjectName("DishCard")
        layout = QVBoxLayout()
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # 第一行：名称 + 价格 + 售罄标签
        name = str(dish.get("name") or "-")
        price = dish.get("price")
        price_str = f"¥{price:.1f}" if isinstance(price, (int, float)) else "-"
        available = dish.get("available", False)
        stock = dish.get("stock", 0)
        stock_str = str(int(stock)) if isinstance(stock, (int, float)) else "-"

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        name_label = QLabel(name)
        name_label.setFont(ui_font(11, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #4a3728;")
        row1.addWidget(name_label)
        row1.addStretch()
        price_label = QLabel(price_str)
        price_label.setFont(ui_font(11, QFont.Weight.Bold))
        price_label.setStyleSheet("color: #b45309;")
        row1.addWidget(price_label)

        stock_badge = QLabel("售" if available else "罄")
        stock_badge.setFont(ui_font(9, QFont.Weight.Bold))
        stock_badge.setFixedHeight(22)
        stock_badge.setMinimumWidth(36)
        stock_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if available:
            stock_badge.setStyleSheet(
                "color: #166534; background: #dcfce7; border-radius: 6px; padding: 1px 8px;"
            )
        else:
            stock_badge.setStyleSheet(
                "color: #991b1b; background: #fee2e2; border-radius: 6px; padding: 1px 8px;"
            )
        row1.addWidget(stock_badge)
        layout.addLayout(row1)

        # 第二行：库存 + 烹饪时间
        cook_time = dish.get("cook_time")
        cook_str = f"{cook_time:.1f} 秒" if isinstance(cook_time, (int, float)) else "-"
        row2 = QHBoxLayout()
        row2.setSpacing(18)
        row2.addWidget(self._small_label(f"库存：{stock_str}"))
        row2.addWidget(self._small_label(f"烹饪：{cook_str}"))
        row2.addStretch()
        layout.addLayout(row2)

        # 第三行：特征标签
        features = dish.get("features")
        if isinstance(features, dict) and features:
            row3 = QHBoxLayout()
            row3.setSpacing(6)
            for key, value in features.items():
                tag = self._feature_tag(key, float(value))
                row3.addWidget(tag)
            row3.addStretch()
            layout.addLayout(row3)

        card.setLayout(layout)
        return card

    @staticmethod
    def _small_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(ui_font(9))
        label.setStyleSheet("color: #78716c;")
        return label

    @staticmethod
    def _feature_tag(key: str, value: float) -> QLabel:
        """将 feature dict 的键值转为中文标签。"""
        name_map = {
            "meat": "荤",
            "veg": "素",
            "spicy": "辣",
            "sweet": "甜",
            "sour": "酸",
            "salty": "咸",
            "light": "清淡",
            "heavy": "重口",
            "hot": "热",
            "cold": "凉",
            "fried": "炸",
            "soup": "汤",
        }
        display = name_map.get(key, key)
        intensity = "●" if value >= 0.6 else "◐" if value >= 0.3 else "○"
        tag = QLabel(f"{display} {intensity}")
        tag.setFont(ui_font(8))
        tag.setStyleSheet(
            "color: #6b7280; background: #f3f4f6; border-radius: 4px; padding: 1px 6px;"
        )
        return tag
