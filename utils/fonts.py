from __future__ import annotations

from functools import lru_cache

from PyQt6.QtGui import QFont, QFontDatabase


PREFERRED_UI_FONT_FAMILIES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "PingFang SC",
    "Hiragino Sans GB",
    "SimHei",
)


@lru_cache(maxsize=1)
def preferred_ui_font_family() -> str:
    available = {family.casefold(): family for family in QFontDatabase.families()}
    for family in PREFERRED_UI_FONT_FAMILIES:
        matched = available.get(family.casefold())
        if matched:
            return matched
    return QFont().defaultFamily() or "Sans Serif"


def ui_font(point_size: int, weight: QFont.Weight | None = None) -> QFont:
    if weight is None:
        return QFont(preferred_ui_font_family(), point_size)
    return QFont(preferred_ui_font_family(), point_size, weight)


def stylesheet_font_family() -> str:
    return preferred_ui_font_family().replace('"', '\\"')
