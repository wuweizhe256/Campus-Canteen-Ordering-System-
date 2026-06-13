from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
    "SimSun",
    "DengXian",
)

_UI_FONT_SCALE = 1.0

BUNDLED_FONT_CANDIDATES = (
    Path("/mnt/c/Windows/Fonts/msyh.ttc"),
    Path("/mnt/c/Windows/Fonts/msyhbd.ttc"),
    Path("/mnt/c/Windows/Fonts/simhei.ttf"),
    Path("/mnt/c/Windows/Fonts/simsun.ttc"),
    Path("/mnt/c/Windows/Fonts/Deng.ttf"),
)


@lru_cache(maxsize=1)
def _load_application_fonts() -> tuple[str, ...]:
    loaded: list[str] = []
    for path in BUNDLED_FONT_CANDIDATES:
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        loaded.extend(QFontDatabase.applicationFontFamilies(font_id))
    return tuple(loaded)


@lru_cache(maxsize=1)
def preferred_ui_font_family() -> str:
    loaded_families = _load_application_fonts()
    available = {family.casefold(): family for family in (*QFontDatabase.families(), *loaded_families)}
    for family in PREFERRED_UI_FONT_FAMILIES:
        matched = available.get(family.casefold())
        if matched:
            return matched
    if loaded_families:
        return loaded_families[0]
    return QFont().defaultFamily() or "Sans Serif"


def ui_font(point_size: int, weight: QFont.Weight | None = None) -> QFont:
    point_size = max(1, round(point_size * _UI_FONT_SCALE))
    if weight is None:
        return QFont(preferred_ui_font_family(), point_size)
    return QFont(preferred_ui_font_family(), point_size, weight)


def stylesheet_font_family() -> str:
    return preferred_ui_font_family().replace('"', '\\"')


def set_ui_font_scale(scale: float) -> None:
    global _UI_FONT_SCALE
    _UI_FONT_SCALE = max(0.8, min(1.6, float(scale)))
