"""仿真结束后弹出的统计结果大窗口。

展示终局信息、全局统计和窗口营收排行（前三名高亮）。
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.entities import RunSummary
from views.ui_widgets import dialog_stylesheet


# ── 小工具函数 ──────────────────────────────────────────────────────────────

def _fmt(value: float | int | None, suffix: str = "", precision: int = 1) -> str:
    """安全格式化数值，None 显示为 "—"."""
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{precision}f}{suffix}"
    return f"{value}{suffix}"


def _pct(value: float | None) -> str:
    """格式化为百分比字符串."""
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _seconds_to_minutes(seconds: float | None) -> str:
    """将秒数格式化为可读的分钟+秒."""
    if seconds is None:
        return "—"
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m > 0:
        return f"{m} 分 {s} 秒"
    return f"{s} 秒"


# ── 主对话框 ──────────────────────────────────────────────────────────────


class SimulationResultDialog(QDialog):
    """仿真结果大窗口。

    通过卡片布局展示终局信息、全局统计指标以及窗口营收排名。
    """

    # 金银铜色
    _MEDAL_COLORS = {
        0: ("#FFD700", "#B8860B", "🥇"),   # 金
        1: ("#C0C0C0", "#707070", "🥈"),   # 银
        2: ("#CD7F32", "#8B4513", "🥉"),   # 铜
    }

    def __init__(
        self,
        frame: dict,
        summary: RunSummary,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("仿真结果")
        self.setModal(False)
        self.setMinimumSize(820, 600)
        self.resize(880, 680)
        self._intro_animation: QPropertyAnimation | None = None

        self._frame = frame
        self._summary = summary
        self._stats: dict = frame.get("stats", {})
        self._stalls: list[dict] = frame.get("stalls", [])

        # 计算窗口营收汇总
        self._stall_revenues: list[dict] = self._build_stall_revenues()

        # ── 构建 UI ──────────────────────────────────────────────────────
        content = QGridLayout()
        content.setContentsMargins(22, 20, 22, 6)
        content.setHorizontalSpacing(16)
        content.setVerticalSpacing(14)

        # 第一行：终局信息 + 全局统计
        content.addWidget(self._card("终局信息", self._endgame_form()), 0, 0)
        content.addWidget(self._card("全局统计", self._global_stats_form()), 0, 1)

        # 第二行：窗口营收排行（跨两列）
        content.addWidget(self._card("窗口营收排行", self._revenue_ranking_widget()), 1, 0, 1, 2)

        content.setColumnStretch(0, 1)
        content.setColumnStretch(1, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.setCenterButtons(True)
        buttons.setContentsMargins(20, 8, 20, 18)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(content)
        layout.addWidget(buttons)
        self.setLayout(layout)

        self._apply_style()
        self.setSizeGripEnabled(True)

    # ── 窗口营收计算 ──────────────────────────────────────────────────────

    def _build_stall_revenues(self) -> list[dict]:
        """从 dish_sales_stats 聚合每个窗口的营收和销量，按营收降序排列。"""
        stall_map: dict[int, dict] = {}

        # 先收集所有窗口的 id -> name 映射
        for stall in self._stalls:
            sid = stall.get("id")
            if isinstance(sid, (int, float)):
                stall_map[int(sid)] = {
                    "stall_id": int(sid),
                    "name": stall.get("name", f"窗口 {int(sid) + 1}"),
                    "revenue": 0.0,
                    "sales_count": 0,
                }

        # 累加各菜品的营收
        for sale in self._stats.get("dish_sales_stats", []):
            sid = sale.get("stall_id")
            if isinstance(sid, (int, float)):
                sid = int(sid)
            else:
                continue
            if sid in stall_map:
                stall_map[sid]["revenue"] += float(sale.get("revenue", 0))
                stall_map[sid]["sales_count"] += int(sale.get("sales_count", 0))

        # 按营收降序排列
        result = sorted(
            stall_map.values(),
            key=lambda s: s["revenue"],
            reverse=True,
        )
        return result

    # ── 卡片容器 ──────────────────────────────────────────────────────────

    def _card(self, title: str, body: QWidget | QFormLayout) -> QFrame:
        card = QFrame()
        card.setObjectName("ConfigCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(39, 31, 22, 18))
        card.setGraphicsEffect(shadow)

        title_label = QLabel(title)
        title_label.setObjectName("ConfigCardTitle")

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 14, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        if isinstance(body, QFormLayout):
            layout.addLayout(body)
        else:
            layout.addWidget(body)
        card.setLayout(layout)
        return card

    def _form_layout(self) -> QFormLayout:
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return form

    # ── 终局信息 ──────────────────────────────────────────────────────────

    def _endgame_form(self) -> QFormLayout:
        form = self._form_layout()
        served = self._frame.get("served_students", 0)
        spawned = self._frame.get("spawned_students", 0)
        serve_rate = (served / spawned * 100) if spawned > 0 else None

        form.addRow("仿真状态", self._value_label(self._summary.status))
        form.addRow("仿真时长", self._value_label(
            f"{self._frame.get('game_time', 0) / 60:.1f} 分钟"
        ))
        form.addRow("生成学生", self._value_label(f"{spawned} 人"))
        form.addRow("完成就餐", self._value_label(f"{served} 人"))
        form.addRow("场内剩余", self._value_label(f"{self._frame.get('active_students', 0)} 人"))
        form.addRow("服务率", self._value_label(
            f"{serve_rate:.1f}%" if serve_rate is not None else "—"
        ))
        return form

    # ── 全局统计 ──────────────────────────────────────────────────────────

    def _global_stats_form(self) -> QFormLayout:
        form = self._form_layout()
        s = self._stats

        form.addRow("平均等待时间", self._value_label(
            _seconds_to_minutes(s.get("avg_wait_time"))
        ))
        form.addRow("平均就餐时间", self._value_label(
            _seconds_to_minutes(s.get("avg_eating_time"))
        ))
        form.addRow("平均总时间", self._value_label(
            _seconds_to_minutes(s.get("avg_total_time"))
        ))
        form.addRow("座位利用率", self._value_label(
            _pct(s.get("seat_utilization"))
        ))
        form.addRow("拥堵指数", self._value_label(
            _fmt(s.get("congestion_index"), precision=3)
        ))
        form.addRow("完成订单", self._value_label(
            _fmt(s.get("completed_order_count"), " 单")
        ))
        form.addRow("取消订单", self._value_label(
            _fmt(s.get("cancelled_order_count"), " 单")
        ))
        form.addRow("同行同座率", self._value_label(
            _pct(s.get("group_same_table_rate"))
        ))
        form.addRow("完成同行组", self._value_label(
            _fmt(s.get("completed_group_count"), " 组")
        ))
        return form

    # ── 窗口营收排行 ──────────────────────────────────────────────────────

    def _revenue_ranking_widget(self) -> QWidget:
        """构建营收排行表格，前三名高亮金银铜色。"""
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 汇总行
        total_revenue = sum(s["revenue"] for s in self._stall_revenues)
        total_sales = sum(s["sales_count"] for s in self._stall_revenues)
        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, 0, 0, 0)
        total_label = QLabel(
            f"全窗口营业额合计：¥{total_revenue:.2f}　｜　总销量：{total_sales} 份"
        )
        total_label.setObjectName("RevenueSummaryLabel")
        summary_row.addWidget(total_label)
        summary_row.addStretch(1)
        layout.addLayout(summary_row)

        # 表格
        table = QTableWidget()
        table.setObjectName("RevenueTable")
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["排名", "窗口名称", "营业额", "销量", "占比"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 列宽
        table.setColumnWidth(0, 56)
        table.setColumnWidth(1, 140)
        table.setColumnWidth(2, 110)
        table.setColumnWidth(3, 80)

        table.setRowCount(len(self._stall_revenues))

        for rank, stall in enumerate(self._stall_revenues):
            row = rank
            rev = stall["revenue"]
            share = (rev / total_revenue * 100) if total_revenue > 0 else 0.0

            items = [
                (str(rank + 1),),
                (stall["name"],),
                (f"¥{rev:.2f}",),
                (f"{stall['sales_count']} 份",),
                (f"{share:.1f}%",),
            ]

            for col, (text,) in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # 前三名特殊样式
                if rank < 3:
                    bg, fg, _medal = self._MEDAL_COLORS[rank]
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                    # 排名列加奖牌图标
                    if col == 0:
                        item.setText(f"{_medal} {rank + 1}")

                table.setItem(row, col, item)

            table.setRowHeight(row, 34)

        layout.addWidget(table)

        # 前三名小结
        if len(self._stall_revenues) >= 3:
            podium = self._stall_revenues[:3]
            podium_text = (
                f"🥇 {podium[0]['name']}　｜　"
                f"🥈 {podium[1]['name']}　｜　"
                f"🥉 {podium[2]['name']}"
            )
        elif len(self._stall_revenues) == 2:
            podium_text = (
                f"🥇 {self._stall_revenues[0]['name']}　｜　"
                f"🥈 {self._stall_revenues[1]['name']}"
            )
        elif len(self._stall_revenues) == 1:
            podium_text = f"🥇 {self._stall_revenues[0]['name']}"
        else:
            podium_text = "暂无窗口数据"

        podium_label = QLabel(f"营收前三名：{podium_text}")
        podium_label.setObjectName("PodiumLabel")
        podium_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(podium_label)

        container.setLayout(layout)
        return container

    def _value_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("ResultValue")
        return label

    # ── 动画 ──────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        QTimer.singleShot(0, self._play_intro_animation)

    def _play_intro_animation(self) -> None:
        end_pos = self.pos()
        self.move(end_pos + QPoint(0, 10))

        position = QPropertyAnimation(self, b"pos", self)
        position.setDuration(220)
        position.setStartValue(end_pos + QPoint(0, 10))
        position.setEndValue(end_pos)
        position.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._intro_animation = position
        self._intro_animation.start()

    # ── 样式 ──────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        base = dialog_stylesheet()
        extra = """
            QLabel#ResultLabel {
                color: #4a5548;
                font: 9pt "Microsoft YaHei UI";
            }
            QLabel#ResultValue {
                color: #17211f;
                font: 700 10pt "Microsoft YaHei UI";
            }
            QLabel#RevenueSummaryLabel {
                color: #33423f;
                font: 700 10pt "Microsoft YaHei UI";
                padding: 4px 0;
            }
            QLabel#PodiumLabel {
                color: #0f5f59;
                font: 900 11pt "Microsoft YaHei UI";
                padding: 6px 0;
            }
            QTableWidget#RevenueTable {
                background: #fffefa;
                border: 1px solid #e2d2be;
                border-radius: 10px;
                gridline-color: #e8e0d0;
                font: 9pt "Microsoft YaHei UI";
            }
            QTableWidget#RevenueTable QHeaderView::section {
                background: #f7efe2;
                color: #33423f;
                font: 800 9pt "Microsoft YaHei UI";
                border: none;
                border-bottom: 2px solid #dccdb8;
                padding: 6px 4px;
            }
            QHeaderView::down-arrow {
                image: none;
            }
            QHeaderView::up-arrow {
                image: none;
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
        """
        self.setStyleSheet(base + extra)
