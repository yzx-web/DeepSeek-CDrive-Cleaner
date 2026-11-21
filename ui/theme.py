# -*- coding: utf-8 -*-
"""全局主题、字体与设计令牌。

设计基调：iOS 控制中心的通透玻璃 + 奶油色暖光 + 克制的蓝紫强调色。
所有颜色、字体、间距集中在这里，避免页面里出现散落的魔法数字。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette


# ---------------------------------------------------------------------------
# 设计令牌
# ---------------------------------------------------------------------------
SPACE = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 20,
    "xl": 24,
    "page": 32,
}
RADIUS = {
    "window": 20,
    "card": 16,
    "control": 12,
    "tag": 8,
    "icon": 10,
}


@dataclass(frozen=True)
class Theme:
    """一套完整的主题颜色快照。"""

    key: str
    is_dark: bool
    name: str
    bg_top: QColor
    bg_bottom: QColor
    glow_violet: QColor
    glow_cyan: QColor
    glow_warm: QColor
    card_top: QColor
    card_bottom: QColor
    card_border: QColor
    card_highlight: QColor
    sidebar_top: QColor
    sidebar_bottom: QColor
    text: QColor
    subtext: QColor
    muted: QColor
    faint: QColor
    accent: QColor
    accent_alt: QColor
    cyan: QColor
    mint: QColor
    orange: QColor
    coral: QColor
    shadow: QColor
    divider: QColor
    input_bg: QColor
    chip_bg: QColor
    selection: QColor
    glass_tint: QColor
    overlay: QColor

    @property
    def accent_gradient(self) -> List[QColor]:
        return [self.accent, self.accent_alt]


def _c(value: str, alpha: int = 255) -> QColor:
    color = QColor(value)
    color.setAlpha(alpha)
    return color


DARK = Theme(
    key="dark",
    is_dark=True,
    name="深色",
    bg_top=_c("#14121F"),
    bg_bottom=_c("#1C1A2E"),
    glow_violet=_c("#7558FF", 72),
    glow_cyan=_c("#2FD3FF", 38),
    glow_warm=_c("#BF5AF2", 42),
    card_top=_c("#FFFFFF", 30),
    card_bottom=_c("#FFFFFF", 17),
    card_border=_c("#FFFFFF", 54),
    card_highlight=_c("#FFFFFF", 72),
    sidebar_top=_c("#FFFFFF", 24),
    sidebar_bottom=_c("#FFFFFF", 12),
    text=_c("#FBFAFF"),
    subtext=_c("#C9C5D8"),
    muted=_c("#9D98B6"),
    faint=_c("#726C8C"),
    accent=_c("#7F7AFF"),
    accent_alt=_c("#C46BFF"),
    cyan=_c("#64D2FF"),
    mint=_c("#30D158"),
    orange=_c("#FF9F0A"),
    coral=_c("#FF453A"),
    shadow=_c("#0A0714", 112),
    divider=_c("#FFFFFF", 16),
    input_bg=_c("#FFFFFF", 22),
    chip_bg=_c("#7F7AFF", 32),
    selection=_c("#7F7AFF", 90),
    glass_tint=_c("#FFFFFF"),
    overlay=_c("#08060F", 190),
)

LIGHT = Theme(
    key="light",
    is_dark=False,
    name="浅色",
    bg_top=_c("#F6F2EB"),
    bg_bottom=_c("#EAE4DA"),
    glow_violet=_c("#B9A8FF", 72),
    glow_cyan=_c("#A5E9F7", 42),
    glow_warm=_c("#FFD59A", 82),
    card_top=_c("#FFFFFF", 148),
    card_bottom=_c("#FFFFFF", 95),
    card_border=_c("#FFFFFF", 210),
    card_highlight=_c("#FFFFFF", 245),
    sidebar_top=_c("#FFFFFF", 135),
    sidebar_bottom=_c("#FFFFFF", 76),
    text=_c("#25212F"),
    subtext=_c("#6A6478"),
    muted=_c("#7F788C"),
    faint=_c("#9A92A4"),
    accent=_c("#5E5CE6"),
    accent_alt=_c("#BF5AF2"),
    cyan=_c("#36B6DE"),
    mint=_c("#25A951"),
    orange=_c("#E8830A"),
    coral=_c("#E94B43"),
    shadow=_c("#7D654C", 58),
    divider=_c("#4A3E31", 20),
    input_bg=_c("#FFFFFF", 150),
    chip_bg=_c("#5E5CE6", 24),
    selection=_c("#5E5CE6", 30),
    glass_tint=_c("#24202B"),
    overlay=_c("#171320", 128),
)

THEMES: Dict[str, Theme] = {"dark": DARK, "light": LIGHT}


# ---------------------------------------------------------------------------
# 字体
# ---------------------------------------------------------------------------
UI_FAMILIES = [
    "SF Pro Text",
    "SF Pro Display",
    "Segoe UI Variable Text",
    "Segoe UI",
    "PingFang SC",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
]
DISPLAY_FAMILIES = [
    "SF Pro Display",
    "Segoe UI Variable Display",
    "Segoe UI",
    "PingFang SC",
    "Microsoft YaHei UI",
    "Noto Sans CJK SC",
]
NUMBER_FAMILIES = [
    "SF Pro Display",
    "Segoe UI Variable Display",
    "Segoe UI",
    "Helvetica Neue",
    "Noto Sans",
]


def app_font(size: int = 14, weight: int = QFont.Weight.Normal, display: bool = False,
             numeric: bool = False) -> QFont:
    """创建遵循全局规范的字体。

    * 数字使用 tabular-nums（Qt 支持时），避免实时刷新时字符宽度跳动。
    * 中文与西文通过 family fallback 选择，Windows 上没有苹方时自动落到微软雅黑。
    """
    family = NUMBER_FAMILIES if numeric else (DISPLAY_FAMILIES if display else UI_FAMILIES)
    font = QFont()
    font.setFamilies(family)
    font.setPixelSize(max(9, int(size)))
    font.setWeight(weight)
    if numeric:
        font.setStyleHint(QFont.StyleHint.SansSerif)
        try:  # Qt 6.7+：开启等宽数字变体
            font.setFeature(QFont.Tag("tnum"), 1)
        except Exception:
            pass
    return font


def set_app_font(app: QGuiApplication) -> None:
    """把默认字体写入 QApplication，保证原生控件也不掉队。"""
    font = app_font(14)
    app.setFont(font)


# ---------------------------------------------------------------------------
# 主题管理
# ---------------------------------------------------------------------------
class ThemeManager(QObject):
    """单例主题控制器：自动读取系统深浅色，并支持手动切换。"""

    changed = Signal(object)
    _instance: "ThemeManager | None" = None

    def __init__(self, app: QGuiApplication) -> None:
        super().__init__()
        self.app = app
        ThemeManager._instance = self
        self._mode = "auto"          # auto / light / dark
        self._system_dark = self._detect_system_dark()
        self._theme = THEMES["dark" if self._system_dark else "light"]
        self._styles = ""
        try:
            self.app.styleHints().colorSchemeChanged.connect(self._on_system_scheme)
        except Exception:
            pass
        self.rebuild_stylesheet()

    # -- 系统检测 ----------------------------------------------------------
    def _detect_system_dark(self) -> bool:
        try:
            scheme = self.app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return True
            if scheme == Qt.ColorScheme.Light:
                return False
        except Exception:
            pass
        # Windows 注册表兜底
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return int(value) == 0
        except Exception:
            return True

    def _on_system_scheme(self, _scheme: object) -> None:
        if self._mode != "auto":
            return
        dark = self._detect_system_dark()
        if dark != self._system_dark:
            self._system_dark = dark
            self._theme = THEMES["dark" if dark else "light"]
            self.rebuild_stylesheet()
            self.changed.emit(self._theme)

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            raise RuntimeError("ThemeManager 尚未初始化")
        return cls._instance

    # -- 对外 API ----------------------------------------------------------
    @property
    def theme(self) -> Theme:
        return self._theme

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """mode: auto / light / dark。"""
        if mode not in {"auto", "light", "dark"}:
            return
        self._mode = mode
        if mode == "auto":
            self._system_dark = self._detect_system_dark()
            selected = "dark" if self._system_dark else "light"
        else:
            selected = mode
        new_theme = THEMES[selected]
        self._theme = new_theme
        self.rebuild_stylesheet()
        self.changed.emit(new_theme)

    def refresh(self) -> None:
        self.rebuild_stylesheet()
        self.changed.emit(self._theme)

    # -- 全局 QSS ----------------------------------------------------------
    def rebuild_stylesheet(self) -> None:
        t = self._theme
        self._styles = f"""
        * {{
            outline: none;
        }}
        QWidget {{
            color: {t.text.name()};
            font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC";
            font-size: 14px;
        }}
        QToolTip {{
            color: {t.text.name()};
            background-color: {t.card_bottom.name()};
            border: 1px solid {t.card_border.name()};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 12px;
        }}
        QScrollArea, QScrollArea > QWidget > QWidget {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 4px 1px 4px 1px;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(128, 122, 148, {38 if not t.is_dark else 50});
            min-height: 36px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: rgba(128, 122, 148, {68 if not t.is_dark else 85});
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent; border: none; height: 0;
        }}
        QScrollBar:horizontal {{
            background: transparent; height: 8px; margin: 1px 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: rgba(128, 122, 148, 50); min-width: 36px; border-radius: 4px;
        }}
        QLineEdit {{
            background: rgba(255,255,255,{28 if t.is_dark else 145});
            border: 1px solid rgba(255,255,255,{42 if t.is_dark else 185});
            border-radius: 10px;
            color: {t.text.name()};
            padding: 8px 12px;
            selection-background-color: {t.accent.name()};
        }}
        QTextEdit {{
            background: rgba(255,255,255,{22 if t.is_dark else 135});
            border: 1px solid rgba(255,255,255,{38 if t.is_dark else 180});
            border-radius: 12px;
            color: {t.text.name()};
            padding: 12px;
            selection-background-color: {t.accent.name()};
        }}
        """
        self.app.setStyleSheet(self._styles)
        set_app_font(self.app)
        self._apply_palette(t)

    def _apply_palette(self, t: Theme) -> None:
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, t.bg_top)
        pal.setColor(QPalette.ColorRole.WindowText, t.text)
        pal.setColor(QPalette.ColorRole.Base, t.card_bottom)
        pal.setColor(QPalette.ColorRole.AlternateBase, t.card_top)
        pal.setColor(QPalette.ColorRole.Text, t.text)
        pal.setColor(QPalette.ColorRole.Button, t.card_bottom)
        pal.setColor(QPalette.ColorRole.ButtonText, t.text)
        pal.setColor(QPalette.ColorRole.Highlight, t.accent)
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        pal.setColor(QPalette.ColorRole.ToolTipBase, t.card_bottom)
        pal.setColor(QPalette.ColorRole.ToolTipText, t.text)
        self.app.setPalette(pal)


def category_color(theme: Theme) -> Dict[str, QColor]:
    """8 类垃圾的 iOS 柔和标签色（饱和度克制，不刺眼）。"""
    return {
        "temp": QColor("#6AC8FF") if theme.is_dark else QColor("#3AAEDB"),
        "recycle": QColor("#A8A7B8") if theme.is_dark else QColor("#8E8C9B"),
        "update": QColor("#64B7FF") if theme.is_dark else QColor("#2988E8"),
        "thumbnail": QColor("#C99BFF") if theme.is_dark else QColor("#9B6DE0"),
        "prefetch": QColor("#FFB867") if theme.is_dark else QColor("#E8902E"),
        "browser": QColor("#5DDE84") if theme.is_dark else QColor("#23A951"),
        "logs": QColor("#FFD86B") if theme.is_dark else QColor("#D8A400"),
        "bigfiles": QColor("#FF8585") if theme.is_dark else QColor("#E45B5B"),
    }


def tint(color: QColor, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c
