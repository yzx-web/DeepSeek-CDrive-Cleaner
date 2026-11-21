# -*- coding: utf-8 -*-
"""毛玻璃视觉组件库。

这里实现的是“有厚度的玻璃”，而不是单纯降低透明度：
  1) 顶部柔和高光模拟反光；
  2) 底部内阴影 + 外投影模拟厚度；
  3) 中间渐变过渡并叠加极细磨砂纹理；
  4) 1px 内描边把玻璃边缘“提亮”。

所有组件均使用 QPainter 手绘，避免 QSS 无法表达的多层光影。
"""
from __future__ import annotations

import math
import random
from typing import Optional

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation,
                            QRect, QRectF, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout,
                               QWidget)

from .icons import Glyph, draw_glyph
from .theme import RADIUS, SPACE, Theme, ThemeManager, app_font, tint


# ---------------------------------------------------------------------------
# 纹理与绘制工具
# ---------------------------------------------------------------------------
_NOISE_CACHE: dict[int, QImage] = {}


def noise_image(dark: bool) -> QImage:
    """生成可平铺的极细颗粒纹理，让玻璃拥有“磨砂”触感。"""
    key = 1 if dark else 0
    if key in _NOISE_CACHE:
        return _NOISE_CACHE[key]
    size = 96
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    rng = random.Random(410)
    p = QPainter(img)
    count = 820
    for _ in range(count):
        x = rng.randrange(size)
        y = rng.randrange(size)
        if dark:
            p.setPen(QColor(255, 255, 255, rng.choice([5, 7, 9, 12])))
        else:
            p.setPen(QColor(38, 30, 28, rng.choice([4, 6, 8])))
        p.drawPoint(x, y)
    p.end()
    _NOISE_CACHE[key] = img
    return img


def draw_glass(p: QPainter, rect: QRectF, theme: Theme, radius: int = RADIUS["card"],
               alpha_boost: int = 0, border: bool = True, noise: bool = True,
               glow: bool = False, tint_color: Optional[QColor] = None) -> None:
    """绘制一块通透的玻璃底板。"""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    # 玻璃本体：白/黑极低透明度，从顶部到底部微渐变
    top = QColor(theme.card_top)
    bottom = QColor(theme.card_bottom)
    if tint_color is not None:
        top = tint(tint_color, min(255, top.alpha() + 4))
        bottom = tint(tint_color, max(0, bottom.alpha() - 4))
    if alpha_boost:
        top.setAlpha(min(255, top.alpha() + alpha_boost))
        bottom.setAlpha(min(255, bottom.alpha() + alpha_boost))
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, top)
    gradient.setColorAt(0.55, bottom)
    gradient.setColorAt(1.0, tint(bottom, max(4, bottom.alpha() - 4)))
    p.fillPath(path, gradient)

    p.save()
    p.setClipPath(path)
    # 左上角反光：一条很淡的斜向高光带
    gloss = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height() * 0.46))
    gloss.setColorAt(0.0, QColor(255, 255, 255, 62 if theme.is_dark else 118))
    gloss.setColorAt(0.45, QColor(255, 255, 255, 14 if theme.is_dark else 34))
    gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.5), gloss)
    # 底部内阴影，制造玻璃厚度的错觉
    inner = QLinearGradient(rect.left(), rect.bottom() - 18, rect.left(), rect.bottom())
    inner.setColorAt(0.0, QColor(0, 0, 0, 0))
    inner.setColorAt(1.0, QColor(8, 5, 20, 28 if theme.is_dark else 12))
    p.fillRect(QRectF(rect.left(), rect.bottom() - 20, rect.width(), 20), inner)
    # 磨砂颗粒
    if noise:
        p.setOpacity(0.28 if theme.is_dark else 0.2)
        p.setBrushOrigin(QPointF(rect.left(), rect.top()))
        p.fillRect(rect, QBrush(noise_image(theme.is_dark)))
    # 可选的角落光晕
    if glow:
        rad = QRadialGradient(rect.right() - 34, rect.top() + 28, rect.width() * 0.55)
        rad.setColorAt(0.0, QColor(theme.accent.red(), theme.accent.green(), theme.accent.blue(), 34))
        rad.setColorAt(1.0, QColor(theme.accent.red(), theme.accent.green(), theme.accent.blue(), 0))
        p.fillRect(rect, rad)
    p.restore()

    if border:
        # 1px 白色内描边，上亮下暗，玻璃边缘才有“切割感”
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(theme.card_border, 1.0))
        p.drawPath(path)
        hi = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + 24))
        hi.setColorAt(0, QColor(theme.card_highlight.red(), theme.card_highlight.green(),
                                theme.card_highlight.blue(), 190 if theme.is_dark else 230))
        hi.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(QPen(QBrush(hi), 1.0))
        p.drawLine(QPointF(rect.left() + radius, rect.top() + 0.55),
                   QPointF(rect.right() - radius, rect.top() + 0.55))
    p.restore()


def draw_shadow(p: QPainter, rect: QRectF, radius: int, color: QColor, spread: int = 18,
                y_offset: int = 8, strength: float = 1.0) -> None:
    """用多层低透明圆角矩形模拟柔软的彩色投影（比纯黑阴影更贵气）。"""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    layers = 8
    for i in range(layers, 0, -1):
        progress = i / layers
        alpha = int(color.alpha() * (1 - progress) * 0.20 * strength)
        if alpha <= 0:
            continue
        grow = spread * progress
        c = QColor(color)
        c.setAlpha(alpha)
        r = QRectF(rect.left() - grow, rect.top() - grow + y_offset * progress,
                   rect.width() + grow * 2, rect.height() + grow * 2)
        path = QPainterPath()
        path.addRoundedRect(r, radius + grow * 0.8, radius + grow * 0.8)
        p.fillPath(path, c)
    p.restore()


def _text(p: QPainter, rect: QRectF, text: str, font: QFont, color: QColor,
          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter) -> None:
    p.save()
    p.setFont(font)
    p.setPen(color)
    p.drawText(rect, int(align), text)
    p.restore()


def format_size(size: float, decimals: int = 1) -> str:
    """把字节数变 humans 可读，并统一为两位有效数字。"""
    if size is None or size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    value = float(size)
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    if idx == 0:
        return f"{int(value)} B"
    if value >= 100:
        return f"{value:.0f} {units[idx]}"
    if value >= 10:
        return f"{value:.1f} {units[idx]}"
    return f"{value:.2f} {units[idx]}" if value < 2 else f"{value:.1f} {units[idx]}"


# ---------------------------------------------------------------------------
# 背景
# ---------------------------------------------------------------------------
class AuroraBackground(QWidget):
    """深色紫夜 / 暖米白晨光，叠加柔和径向光晕与磨砂颗粒。"""

    def __init__(self, theme_manager: ThemeManager, parent: Optional[QWidget] = None,
                 radius: int = RADIUS["window"]) -> None:
        super().__init__(parent)
        self.tm = theme_manager
        self.radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.tm.changed.connect(self.update)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(r), self.radius, self.radius)
        p.setClipPath(clip)
        # 基础渐变
        grad = QLinearGradient(0, 0, r.width() * 0.2, r.height())
        grad.setColorAt(0, t.bg_top)
        grad.setColorAt(0.58, t.bg_bottom)
        grad.setColorAt(1, t.bg_bottom)
        p.fillRect(r, grad)
        # 三团大范围光晕（柔和、低饱和）
        if t.is_dark:
            self._radial(p, r.width() * 0.22, r.height() * 0.1, r.width() * 0.55, t.glow_violet, 120)
            self._radial(p, r.width() * 0.86, r.height() * 0.78, r.width() * 0.46, t.glow_cyan, 52)
            self._radial(p, r.width() * 0.66, r.height() * 0.18, r.width() * 0.34, t.glow_warm, 44)
        else:
            self._radial(p, r.width() * 0.18, -20, r.width() * 0.5, t.glow_warm, 118)
            self._radial(p, r.width() * 0.9, r.height() * 0.1, r.width() * 0.4, t.glow_violet, 63)
            self._radial(p, r.width() * 0.72, r.height() * 0.88, r.width() * 0.36, t.glow_cyan, 38)
        # 一条极淡的弧形丝带，增加“空气流动”感
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.moveTo(-20, r.height() * 0.70)
        path.cubicTo(r.width() * 0.22, r.height() * 0.48,
                     r.width() * 0.52, r.height() * 0.88,
                     r.width() + 30, r.height() * 0.52)
        path.lineTo(r.width() + 30, r.height() + 20)
        path.lineTo(-20, r.height() + 20)
        path.closeSubpath()
        ribbon = QLinearGradient(0, r.height() * 0.5, r.width(), r.height() * 0.8)
        ribbon.setColorAt(0, QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 0))
        ribbon.setColorAt(0.45, QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 18 if t.is_dark else 12))
        ribbon.setColorAt(1, QColor(t.cyan.red(), t.cyan.green(), t.cyan.blue(), 0))
        p.fillPath(path, ribbon)
        # 噪声
        p.setOpacity(0.22 if t.is_dark else 0.18)
        p.setBrushOrigin(0, 0)
        p.fillRect(r, QBrush(noise_image(t.is_dark)))
        p.setOpacity(1)
        # 边缘暗角
        v = QRadialGradient(r.width() / 2, r.height() / 2, max(r.width(), r.height()) * 0.82)
        v.setColorAt(0.5, QColor(0, 0, 0, 0))
        v.setColorAt(1, QColor(0, 0, 0, 38 if t.is_dark else 12))
        p.fillRect(r, v)
        # 外描边
        p.setPen(QPen(QColor(255, 255, 255, 45 if t.is_dark else 120), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), self.radius, self.radius)

    @staticmethod
    def _radial(p: QPainter, x: float, y: float, radius: float, color: QColor,
                alpha: int) -> None:
        c = QColor(color)
        c.setAlpha(alpha)
        grad = QRadialGradient(x, y, radius)
        grad.setColorAt(0, c)
        c2 = QColor(color)
        c2.setAlpha(max(0, alpha // 3))
        grad.setColorAt(0.55, c2)
        c3 = QColor(color)
        c3.setAlpha(0)
        grad.setColorAt(1, c3)
        p.fillRect(QRectF(x - radius, y - radius, radius * 2, radius * 2), grad)


# ---------------------------------------------------------------------------
# 卡片
# ---------------------------------------------------------------------------
class GlassCard(QFrame):
    """基础玻璃卡片，可选悬浮抬升。"""

    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None, radius: int = RADIUS["card"],
                 padding: int = RADIUS["card"] + 4, hover: bool = False,
                 glow: bool = False, tint_color: Optional[QColor] = None,
                 shadow: bool = True) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.radius = radius
        self.hover_enabled = hover
        self.use_glow = glow
        self.tint_color = tint_color
        self._hover_t = 0.0
        self._shadow: Optional[QGraphicsDropShadowEffect] = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(padding, padding, padding, padding)
        self.layout_.setSpacing(12)
        if shadow:
            self._shadow = QGraphicsDropShadowEffect(self)
            self._shadow.setBlurRadius(34)
            self._shadow.setOffset(0, 10)
            c = QColor(self.tm.theme.shadow)
            c.setAlpha(84 if not self.tm.theme.is_dark else 112)
            self._shadow.setColor(c)
            self.setGraphicsEffect(self._shadow)
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if hover:
            self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.tm.changed.connect(self._on_theme)

    def _on_theme(self, *_args) -> None:
        if self._shadow is not None:
            c = QColor(self.tm.theme.shadow)
            c.setAlpha(112 if self.tm.theme.is_dark else 70)
            self._shadow.setColor(c)
        self.update()

    def get_hover_progress(self) -> float:
        return self._hover_t

    def set_hover_progress(self, value: float) -> None:
        self._hover_t = value
        if self._shadow is not None:
            base = 34 if self.tm.theme.is_dark else 30
            self._shadow.setBlurRadius(base + 16 * value)
            self._shadow.setOffset(0, 10 + 5 * value)
            c = QColor(self.tm.theme.shadow)
            c.setAlpha(int((112 if self.tm.theme.is_dark else 72) * (0.82 + 0.22 * value)))
            self._shadow.setColor(c)
        self.update()

    hoverProgress = Property(float, get_hover_progress, set_hover_progress)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        if self.hover_enabled:
            self._hover_anim.stop()
            self._hover_anim.setEndValue(1.0)
            self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        if self.hover_enabled:
            self._hover_anim.stop()
            self._hover_anim.setEndValue(0.0)
            self._hover_anim.start()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        draw_glass(p, QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                   self.tm.theme, self.radius, alpha_boost=int(14 * self._hover_t),
                   glow=self.use_glow, tint_color=self.tint_color)


class TintedGlass(GlassCard):
    """带类别色调的卡片，透明底色的色相与内容呼应。"""


# ---------------------------------------------------------------------------
# 文本与数字
# ---------------------------------------------------------------------------
class Label(QLabel):
    def __init__(self, text: str = "", size: int = 14, weight: int = QFont.Weight.Normal,
                 color: Optional[QColor] = None, parent: Optional[QWidget] = None,
                 line_height: float = 1.5, display: bool = False,
                 numeric: bool = False) -> None:
        super().__init__(text, parent)
        self.tm = ThemeManager.instance()
        self._size = size
        self._weight = weight
        self._explicit_color = QColor(color) if color else None
        self._color_role = None
        if self._explicit_color is not None:
            for role in ("text", "subtext", "muted", "faint", "accent", "cyan", "mint", "orange", "coral"):
                token = getattr(self.tm.theme, role)
                if QColor(token) == self._explicit_color:
                    self._color_role = role
                    self._explicit_color = None
                    break
        self._display = display
        self._numeric = numeric
        self.setFont(app_font(size, weight, display, numeric=numeric))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setWordWrap(True)
        self._apply_color()
        self.tm.changed.connect(self._apply_color)

    def _apply_color(self, *_args) -> None:
        color = getattr(self.tm.theme, self._color_role) if self._color_role else (self._explicit_color or self.tm.theme.text)
        self.setStyleSheet(f"color: rgba({color.red()},{color.green()},{color.blue()},{color.alpha()});"
                           f"background: transparent; line-height: {int(self._size * 1.5)}px;")

    def set_color(self, color: QColor) -> None:
        self._explicit_color = QColor(color)
        self._color_role = None
        for role in ("text", "subtext", "muted", "faint", "accent", "cyan", "mint", "orange", "coral"):
            token = getattr(self.tm.theme, role)
            if QColor(token) == self._explicit_color:
                self._color_role = role
                self._explicit_color = None
                break
        self._apply_color()

    def set_size(self, size: int) -> None:
        self._size = size
        self.setFont(app_font(size, self._weight, self._display, numeric=self._numeric))
        self._apply_color()


class Eyebrow(QLabel):
    """小号全大写标签，增加信息层次。"""

    def __init__(self, text: str, color: Optional[QColor] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(text.upper(), parent)
        self.tm = ThemeManager.instance()
        font = app_font(10, QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        self.setFont(font)
        self._color = color or self.tm.theme.muted
        self._apply()
        self.tm.changed.connect(self._apply)

    def _apply(self, *_args) -> None:
        c = self._color if self._color else self.tm.theme.muted
        self.setStyleSheet(f"color: rgba({c.red()},{c.green()},{c.blue()},{c.alpha()});"
                           "background: transparent;")


class DataNumber(QWidget):
    """超大号核心数字，支持数字滚动与 tabular-nums。"""

    def __init__(self, value: float = 0.0, size: int = 44, suffix: str = "",
                 prefix: str = "", color: Optional[QColor] = None,
                 parent: Optional[QWidget] = None, duration: int = 420) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self._value = float(value)
        self._target = float(value)
        self._size = size
        self.suffix = suffix
        self.prefix = prefix
        self._explicit_color = QColor(color) if color else None
        self._decimals = 1 if any(u in suffix for u in ("GB", "MB", "TB")) else 0
        self._anim = QPropertyAnimation(self, b"displayValue", self)
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(int(size * 1.12))
        self.tm.changed.connect(self.update)

    def sizeHint(self) -> QSize:  # noqa: N802
        font = app_font(self._size, QFont.Weight.Bold, True, numeric=True)
        fm = QFontMetrics(font)
        text = self.prefix + self._format(self._target) + self.suffix
        return QSize(fm.horizontalAdvance(text) + 8, int(self._size * 1.2))

    def _format(self, value: float) -> str:
        if self._decimals:
            return f"{value:.1f}"
        return f"{value:,.0f}"

    def get_display_value(self) -> float:
        return self._value

    def set_display_value(self, value: float) -> None:
        self._value = value
        self.updateGeometry()
        self.update()

    displayValue = Property(float, get_display_value, set_display_value)

    def set_value(self, value: float, animate: bool = True) -> None:
        self._target = float(value)
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._value)
            self._anim.setEndValue(self._target)
            self._anim.start()
        else:
            self.set_display_value(self._target)

    def value(self) -> float:
        return self._target

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = self._explicit_color or self.tm.theme.text
        big = app_font(self._size, QFont.Weight.Bold, True, numeric=True)
        small = app_font(max(12, int(self._size * 0.34)), QFont.Weight.DemiBold, True, numeric=True)
        text = self.prefix + self._format(self._value)
        fm_big = QFontMetrics(big)
        w_big = fm_big.horizontalAdvance(text)
        w_small = QFontMetrics(small).horizontalAdvance(self.suffix) if self.suffix else 0
        x = 2
        baseline_y = (self.height() + fm_big.ascent() - fm_big.descent()) / 2
        p.setFont(big)
        p.setPen(color)
        p.drawText(QPointF(x, baseline_y), text)
        if self.suffix:
            p.setFont(small)
            c = QColor(color)
            c.setAlpha(200)
            p.setPen(c)
            p.drawText(QPointF(x + w_big + 5, baseline_y - self._size * 0.03), self.suffix)


class AnimatedCounter(QLabel):
    """常规字号计数，用于列表等场景。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self._value = 0
        self._target = 0
        self._suffix = ""
        self.tm.changed.connect(self.update)
        self.setFont(app_font(12, QFont.Weight.DemiBold, numeric=True))

    def set_value(self, value: int, suffix: str = "") -> None:
        self._target = value
        self._suffix = suffix
        self.setFont(app_font(12, QFont.Weight.DemiBold, numeric=True))
        self.setStyleSheet(f"color: {self.tm.theme.subtext.name()}; background: transparent;")
        self.setText(f"{value}{suffix}")


# ---------------------------------------------------------------------------
# 按钮：实体玻璃按键
# ---------------------------------------------------------------------------
class GlassButton(QAbstractButton):
    """具有真实厚度与按压反馈的玻璃按钮。

    kind: primary / secondary / danger / ghost / quiet
    """

    def __init__(self, text: str, kind: str = "secondary", icon: Optional[str] = None,
                 parent: Optional[QWidget] = None, height: int = 46,
                 min_width: int = 0, compact: bool = False) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.kind = kind
        self.icon_name = icon
        self._hover = 0.0
        self._press = 0.0
        self._sweep = 0.0
        self._text = text
        self._height = height
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setText(text)
        self.setAccessibleName(text)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(height)
        if min_width:
            self.setMinimumWidth(min_width)
        self._hover_anim = QPropertyAnimation(self, b"hoverAmount", self)
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._press_anim = QPropertyAnimation(self, b"pressAmount", self)
        self._press_anim.setDuration(90)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._sweep_anim = QPropertyAnimation(self, b"sweepOffset", self)
        self._sweep_anim.setDuration(1700)
        self._sweep_anim.setStartValue(-0.45)
        self._sweep_anim.setEndValue(1.5)
        self._sweep_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        if kind == "primary":
            self._sweep_timer = QTimer(self)
            self._sweep_timer.timeout.connect(self._start_sweep)
            self._sweep_timer.start(3600)
            QTimer.singleShot(300, self._start_sweep)
        else:
            self._sweep_timer = None
        self.tm.changed.connect(self.update)
        self.pressed.connect(self._pressed)
        self.released.connect(self._released)
        font = app_font(13 if compact else 14, QFont.Weight.DemiBold)
        self.setFont(font)

    # 属性动画
    def get_hover(self) -> float:
        return self._hover

    def set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hoverAmount = Property(float, get_hover, set_hover)

    def get_press(self) -> float:
        return self._press

    def set_press(self, value: float) -> None:
        self._press = value
        self.update()

    pressAmount = Property(float, get_press, set_press)

    def get_sweep(self) -> float:
        return self._sweep

    def set_sweep(self, value: float) -> None:
        self._sweep = value
        self.update()

    sweepOffset = Property(float, get_sweep, set_sweep)

    def _start_sweep(self) -> None:
        if not self.isVisible():
            return
        self._sweep_anim.stop()
        self._sweep_anim.start()

    def _pressed(self) -> None:
        self._press_anim.stop()
        self._press_anim.setEndValue(1)
        self._press_anim.start()

    def _released(self) -> None:
        self._press_anim.stop()
        self._press_anim.setEndValue(0)
        self._press_anim.start()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover_anim.stop()
        self._hover_anim.setEndValue(1)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_anim.stop()
        self._hover_anim.setEndValue(0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def setText(self, text: str) -> None:  # noqa: N802
        self._text = text
        self.setAccessibleName(text)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        icon_space = 24 if self.icon_name else 0
        return QSize(fm.horizontalAdvance(self._text) + 44 + icon_space, self._height)

    def _body_rect(self) -> QRectF:
        # 上方留 3px 给高光，下方留 7px 给投影；按下时整体下沉 1px
        press = self._press * 1.1
        return QRectF(2.0, 3.0 + press, self.width() - 4.0, self.height() - 10.0 - press)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        body = self._body_rect()
        radius = RADIUS["control"]
        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)
        enabled = self.isEnabled()
        if not enabled:
            p.setOpacity(0.42)
        primary = self.kind == "primary"
        danger = self.kind == "danger"
        ghost = self.kind in ("ghost", "quiet")

        # 1) 底部外投影：按钮离开桌面，才像实体
        if not ghost:
            shadow = QColor(t.shadow)
            shadow.setAlpha(int((100 if t.is_dark else 56) * (1 - 0.35 * self._press)))
            for i in range(4, 0, -1):
                c = QColor(shadow)
                c.setAlpha(int(shadow.alpha() * (i / 4) * 0.25))
                p.setBrush(c)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(body.adjusted(-i * 0.6, -i * 0.4 + 3 + i,
                                               i * 0.6, i * 1.2 + 3), radius + i, radius + i)

        # 2) 中间渐变：主按钮用 iOS 蓝紫；次级按钮与背景环境色相呼应
        if primary:
            grad = QLinearGradient(body.topLeft(), body.bottomRight())
            grad.setColorAt(0, QColor("#706CFF"))
            grad.setColorAt(0.45, QColor("#8059F5"))
            grad.setColorAt(1, QColor("#C05AF6"))
            p.fillPath(path, grad)
            # 底部紫色厚度
            thickness = QLinearGradient(body.left(), body.bottom() - 8, body.left(), body.bottom())
            thickness.setColorAt(0, QColor(52, 26, 120, 0))
            thickness.setColorAt(1, QColor(42, 14, 104, 150))
            p.save()
            p.setClipPath(path)
            p.fillRect(QRectF(body.left(), body.bottom() - 10, body.width(), 10), thickness)
            p.restore()
        elif danger:
            p.fillPath(path, QColor(255, 69, 58, 34 if t.is_dark else 20))
        elif ghost:
            p.fillPath(path, QColor(255, 255, 255, 18 if t.is_dark else 0))
        else:
            # 次级玻璃：用当前背景的灰米色做半透明底，不“飘”成纯白贴纸
            base_top = QColor(t.card_top)
            base_top.setAlpha(58 if t.is_dark else 138)
            base_bottom = QColor(t.card_bottom)
            base_bottom.setAlpha(30 if t.is_dark else 90)
            grad = QLinearGradient(body.topLeft(), body.bottomLeft())
            grad.setColorAt(0, base_top)
            grad.setColorAt(1, base_bottom)
            p.fillPath(path, grad)

        # 3) 顶部高光：左上宽、右下窄，像光从左上照到玻璃
        p.save()
        p.setClipPath(path)
        gloss = QLinearGradient(body.topLeft(), QPointF(body.left(), body.top() + body.height() * 0.55))
        gloss.setColorAt(0, QColor(255, 255, 255, 98 if primary else (62 if t.is_dark else 120)))
        gloss.setColorAt(0.5, QColor(255, 255, 255, 24 if primary else 20))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(body.left(), body.top(), body.width(), body.height() * 0.58), gloss)
        # 细腻磨砂纹理（斜向 45° 的极淡发丝线）
        p.setOpacity(0.35)
        texture = QLinearGradient(body.topLeft(), body.bottomRight())
        step_color = QColor(255, 255, 255, 13 if primary or not t.is_dark else 9)
        pen = QPen(step_color, 0.6)
        p.setPen(pen)
        spacing = 7
        for offset in range(-int(body.height()), int(body.width()) + int(body.height()), spacing):
            p.drawLine(QPointF(body.left() + offset, body.top()),
                       QPointF(body.left() + offset - body.height(), body.bottom()))
        p.setOpacity(1)
        # 周期性扫光
        if primary:
            width = body.width() * 0.44
            x = body.left() - width + (body.width() + width * 2) * self._sweep
            sweep = QLinearGradient(x, 0, x + width, 0)
            sweep.setColorAt(0, QColor(255, 255, 255, 0))
            sweep.setColorAt(0.5, QColor(255, 255, 255, 44))
            sweep.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(QRectF(x, body.top(), width, body.height()),
                       QBrush(sweep))
        p.restore()

        # 4) 1px 内描边 + 顶边高光线
        border = QColor(255, 255, 255, 150 if t.is_dark else 205) if not danger else QColor(t.coral)
        if primary:
            border = QColor(255, 255, 255, 138)
        p.setPen(QPen(border, 1.1 if not danger else 1.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        if not danger and not ghost:
            p.setPen(QPen(QColor(255, 255, 255, 132), 0.9))
            p.drawLine(QPointF(body.left() + radius * 0.7, body.top() + 0.8),
                       QPointF(body.right() - radius * 0.7, body.top() + 0.8))

        # 5) 文本与图标
        text_color = QColor("#FFFFFF") if primary else (t.coral if danger else t.text)
        if ghost:
            text_color = QColor(t.subtext)
        if not enabled:
            text_color.setAlpha(150)
        icon_size = 18
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self._text)
        total_w = text_w + (icon_size + 9 if self.icon_name else 0)
        start_x = body.left() + (body.width() - total_w) / 2
        center_y = body.center().y() - 0.5
        if self.icon_name:
            icon_rect = QRectF(start_x, center_y - icon_size / 2, icon_size, icon_size)
            draw_glyph(p, self.icon_name, icon_rect, text_color, 1.8)
            start_x += icon_size + 9
        p.setFont(self.font())
        p.setPen(text_color)
        p.drawText(QRectF(start_x, body.top(), text_w + 4, body.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self._text)
        p.setOpacity(1)
        p.end()


class IconButton(QAbstractButton):
    """圆形玻璃图标按钮，用于窗口控制与次要操作。"""

    def __init__(self, icon: str, size: int = 34, danger: bool = False,
                 parent: Optional[QWidget] = None, tooltip: str = "") -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.icon = icon
        self.danger = danger
        self._hover = 0.0
        self._press = 0.0
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self._anim = QPropertyAnimation(self, b"hoverAmount", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.tm.changed.connect(self.update)

    def get_hover(self) -> float:
        return self._hover

    def set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hoverAmount = Property(float, get_hover, set_hover)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._anim.stop()
        self._anim.setEndValue(1)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._anim.stop()
        self._anim.setEndValue(0)
        self._anim.start()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        base = QColor(255, 255, 255, 20 if t.is_dark else 120)
        if self.danger:
            base = QColor(t.coral.red(), t.coral.green(), t.coral.blue(), 30 + int(20 * self._hover))
        elif self._hover > 0:
            base.setAlpha(min(255, base.alpha() + int(22 * self._hover)))
        p.setBrush(base)
        p.setPen(QPen(QColor(255, 255, 255, 55 if t.is_dark else 160), 1))
        p.drawEllipse(r)
        # 顶部高光
        gloss = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
        gloss.setColorAt(0, QColor(255, 255, 255, 50 + int(30 * self._hover)))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(gloss))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(r.adjusted(1, 1, -1, -1))
        color = t.coral if self.danger else t.subtext
        if self._hover > 0:
            color = t.coral if self.danger else t.text
        draw_glyph(p, self.icon, QRectF(r.center().x() - 8, r.center().y() - 8, 16, 16),
                   color, 1.6)


# ---------------------------------------------------------------------------
# 开关
# ---------------------------------------------------------------------------
class Switch(QAbstractButton):
    """iOS 风格开关，带弹性滑块。"""

    def __init__(self, checked: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(48, 28)
        self._knob = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.toggled.connect(self._on_toggle)
        self.tm.changed.connect(self.update)

    def get_knob(self) -> float:
        return self._knob

    def set_knob(self, value: float) -> None:
        self._knob = value
        self.update()

    knobPos = Property(float, get_knob, set_knob)

    def _on_toggle(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def hitButton(self, pos: QPoint) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(1, 3, self.width() - 2, self.height() - 6)
        off = QColor(120, 115, 138, 120 if t.is_dark else 80)
        on = QColor(t.accent)
        blend = self._knob
        c = QColor(
            int(off.red() + (on.red() - off.red()) * blend),
            int(off.green() + (on.green() - off.green()) * blend),
            int(off.blue() + (on.blue() - off.blue()) * blend),
            int(off.alpha() + (on.alpha() - off.alpha()) * blend),
        )
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0, c.lighter(112) if blend > 0.1 else c)
        grad.setColorAt(1, c.darker(108) if blend > 0.1 else c)
        p.setBrush(grad)
        p.setPen(QPen(QColor(255, 255, 255, 65 if t.is_dark else 130), 1))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        # 高光
        p.setPen(Qt.PenStyle.NoPen)
        gloss = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
        gloss.setColorAt(0, QColor(255, 255, 255, 60))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(gloss)
        p.drawRoundedRect(r.adjusted(4, 2, -4, -r.height() / 2), r.height() / 2 - 2, r.height() / 2 - 2)
        knob_r = 11.0
        x = 4 + (r.width() - knob_r * 2 - 8) * blend
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QPen(QColor(0, 0, 0, 26), 0.8))
        p.drawEllipse(QPointF(r.left() + 4 + knob_r + (r.width() - knob_r * 2 - 8) * blend,
                             r.center().y()), knob_r, knob_r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawEllipse(QPointF(r.left() + 4 + knob_r + (r.width() - knob_r * 2 - 8) * blend - 2,
                             r.center().y() - 3), 3.5, 2.4)


# ---------------------------------------------------------------------------
# 进度环
# ---------------------------------------------------------------------------
class ProgressRing(QWidget):
    """玻璃轨道 + 蓝紫渐变弧线，中心可显示大数字与说明。"""

    def __init__(self, diameter: int = 280, line_width: int = 16,
                 value_text: str = "0", unit: str = "%", caption: str = "",
                 subtitle: str = "", parent: Optional[QWidget] = None,
                 big_size: int = 46) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.setFixedSize(diameter, diameter)
        self.line_width = line_width
        self.value_text = value_text
        self.unit = unit
        self.caption = caption
        self.subtitle = subtitle
        self.big_size = big_size
        self._progress = 0.0
        self._target = 0.0
        self._anim = QPropertyAnimation(self, b"displayProgress", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.tm.changed.connect(self.update)

    def get_progress(self) -> float:
        return self._progress

    def set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, value))
        self.update()

    displayProgress = Property(float, get_progress, set_progress)

    def set_value(self, progress: float, value_text: Optional[str] = None,
                  unit: Optional[str] = None, caption: Optional[str] = None,
                  subtitle: Optional[str] = None, animate: bool = True) -> None:
        self._target = max(0.0, min(1.0, progress))
        if value_text is not None:
            self.value_text = value_text
        if unit is not None:
            self.unit = unit
        if caption is not None:
            self.caption = caption
        if subtitle is not None:
            self.subtitle = subtitle
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._progress)
            self._anim.setEndValue(self._target)
            self._anim.start()
        else:
            self.set_progress(self._target)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = self.height()
        lw = self.line_width
        outer = QRectF(lw / 2 + 3, lw / 2 + 3, w - lw - 6, h - lw - 6)
        # 玻璃外环（轨道）
        p.setBrush(QColor(255, 255, 255, 13 if t.is_dark else 58))
        p.setPen(QPen(QColor(255, 255, 255, 50 if t.is_dark else 120), 1))
        p.drawEllipse(outer)
        # 轨道内阴影
        inner = outer.adjusted(lw * 0.8, lw * 0.8, -lw * 0.8, -lw * 0.8)
        p.setBrush(QColor(0, 0, 0, 0))
        p.setPen(QPen(QColor(255, 255, 255, 18 if t.is_dark else 40), 1))
        p.drawEllipse(inner)
        track = outer.adjusted(lw / 2, lw / 2, -lw / 2, -lw / 2)
        path = QPainterPath()
        path.addEllipse(track)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 35 if t.is_dark else 90), lw * 0.55))
        p.drawPath(path)
        # 进度弧：先画外发光，再画本体
        start_angle = 90 * 16
        span = -int(360 * 16 * self._progress)
        if self._progress > 0.002:
            glow_pen = QPen(QColor(t.accent.red(), t.accent.green(), t.accent.blue(),
                                   45 if t.is_dark else 36), lw + 8)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(glow_pen)
            p.drawArc(track, start_angle, span)
            grad = QLinearGradient(track.left(), track.bottom(), track.right(), track.top())
            grad.setColorAt(0.0, QColor("#55C7FF"))
            grad.setColorAt(0.42, QColor("#7772FF"))
            grad.setColorAt(1.0, QColor("#C963FF"))
            pen = QPen(grad, lw)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(track, start_angle, span)
            # 弧线头部的小光点 + 高光
            angle = math.radians(90 - 360 * self._progress)
            cx = track.center().x() + math.cos(angle) * track.width() / 2
            cy = track.center().y() - math.sin(angle) * track.height() / 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 170))
            p.drawEllipse(QPointF(cx, cy), lw * 0.16, lw * 0.16)
        # 中心信息
        center = QRectF(0, 0, w, h)
        value_font = app_font(self.big_size, QFont.Weight.Bold, True, numeric=True)
        unit_font = app_font(max(12, int(self.big_size * 0.34)), QFont.Weight.DemiBold, True, numeric=True)
        cap_font = app_font(12, QFont.Weight.DemiBold)
        sub_font = app_font(11, QFont.Weight.Normal)
        fm_value = QFontMetrics(value_font)
        value_w = fm_value.horizontalAdvance(self.value_text)
        unit_w = QFontMetrics(unit_font).horizontalAdvance(self.unit)
        total_w = value_w + (unit_w + 4 if self.unit else 0)
        center_y = h / 2 - (10 if self.caption else 0)
        p.setFont(value_font)
        p.setPen(t.text)
        p.drawText(QPointF(w / 2 - total_w / 2, center_y + fm_value.ascent() / 2 - 6), self.value_text)
        if self.unit:
            p.setFont(unit_font)
            p.setPen(QColor(t.subtext))
            p.drawText(QPointF(w / 2 - total_w / 2 + value_w + 4,
                               center_y + fm_value.ascent() / 2 - 10), self.unit)
        if self.caption:
            p.setFont(cap_font)
            p.setPen(QColor(t.text))
            p.drawText(QRectF(0, center_y + fm_value.descent() + 2, w, 24),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), self.caption)
        if self.subtitle:
            p.setFont(sub_font)
            p.setPen(QColor(t.muted))
            p.drawText(QRectF(0, center_y + fm_value.descent() + 28, w, 22),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), self.subtitle)


# ---------------------------------------------------------------------------
# 模态框 / Toast / 骨架
# ---------------------------------------------------------------------------
class GlassModal(QWidget):
    """窗口内遮罩式毛玻璃弹窗，带缩放淡入。

    用窗口内 overlay 而非独立 QDialog，这样可以覆盖整个界面并保持圆角与背景一致。
    """

    closed = Signal()

    def __init__(self, host: QWidget, width: int = 480, padding: int = 28,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(host)
        self.tm = ThemeManager.instance()
        self.host = host
        self.radius = RADIUS["window"]
        self.modal_width = width
        self.danger = False
        self.dismissable = True
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._dim = 0.0
        self._dim_anim = QPropertyAnimation(self, b"dimProgress", self)
        self._dim_anim.setDuration(220)
        self._dim_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._content = QWidget(self)
        self._content.setFixedWidth(width)
        self._card = QWidget(self._content)
        self._card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._layout = QVBoxLayout(self._card)
        self._layout.setContentsMargins(padding, padding, padding, padding)
        self._layout.setSpacing(16)
        outer = QVBoxLayout(self._content)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.addWidget(self._card)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._center = QHBoxLayout()
        self._center.addStretch(1)
        self._center.addWidget(self._content, 0)
        self._center.addStretch(1)
        self._root.addStretch(1)
        self._root.addLayout(self._center)
        self._root.addStretch(1)
        self._content_effect = QGraphicsDropShadowEffect(self._card)
        self._content_effect.setBlurRadius(52)
        c = QColor(t.shadow)
        c.setAlpha(150 if not t.is_dark else 190)
        self._content_effect.setColor(c)
        self._content_effect.setOffset(0, 18)
        self._content.setGraphicsEffect(self._content_effect)
        self.hide()

    @property
    def layout_(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_layout(self, layout: QLayout) -> None:  # type: ignore[override]
        self._layout.addLayout(layout)

    def get_dim(self) -> float:
        return self._dim

    def set_dim(self, value: float) -> None:
        self._dim = value
        self.update()

    dimProgress = Property(float, get_dim, set_dim)

    def set_danger(self, value: bool = True) -> None:
        self.danger = value
        self.update()

    def show_modal(self) -> None:
        if self.host is None:
            return
        self.setGeometry(self.host.rect())
        self._content_effect.setEnabled(True)
        self.raise_()
        self.show()
        self.setFocus()
        self._dim_anim.stop()
        self._dim_anim.setStartValue(0.0)
        self._dim_anim.setEndValue(1.0)
        self._dim_anim.start()

    def close_modal(self) -> None:
        anim = QPropertyAnimation(self, b"dimProgress", self)
        anim.setDuration(170)
        anim.setStartValue(self._dim)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.hide)
        anim.finished.connect(self.closed.emit)
        anim.start()
        self._closing_anim = anim

    def resizeEvent(self, event) -> None:  # noqa: N802
        # 让 _content 在可用高度内自适应，避免内容过多被裁切
        self._content.setMaximumHeight(max(200, self.height() - 36))
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.dismissable and not self._content.geometry().contains(event.position().toPoint()):
            self.close_modal()
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_modal()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        t = self.tm.theme
        dim = QColor(t.overlay)
        dim.setAlpha(int(185 * self._dim))
        p.fillRect(self.rect(), dim)
        # 卡片玻璃
        rect = QRectF(self._content.geometry()).adjusted(18, 18, -18, -18)
        draw_shadow(p, rect, self.radius + 4, QColor(t.shadow), spread=28, y_offset=16,
                    strength=self._dim)
        draw_glass(p, rect, t, self.radius + 4, alpha_boost=24, glow=True,
                   border=True, noise=True)
        if self.danger:
            c = QColor(t.coral)
            c.setAlpha(135)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(c, 1.4))
            p.drawRoundedRect(rect.adjusted(0.8, 0.8, -0.8, -0.8), self.radius + 4, self.radius + 4)


class Toast(QWidget):
    """底部居中的轻提示。"""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.tm = ThemeManager.instance()
        self.host = host
        self.message = ""
        self._opacity = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._anim = QPropertyAnimation(self, b"opacityValue", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def get_opacity(self) -> float:
        return self._opacity

    def set_opacity(self, value: float) -> None:
        self._opacity = value
        self.update()

    opacityValue = Property(float, get_opacity, set_opacity)

    def show_message(self, message: str, duration: int = 2600) -> None:
        self.message = message
        self.setFixedHeight(46)
        fm = QFontMetrics(app_font(13, QFont.Weight.DemiBold))
        self.setFixedWidth(min(720, max(220, fm.horizontalAdvance(message) + 84)))
        self.reposition()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(duration)

    def reposition(self) -> None:
        x = (self.host.width() - self.width()) // 2
        y = self.host.height() - self.height() - 34
        self.move(x, y)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(0.0)
        self._anim.start()
        self._anim.finished.connect(lambda: self.hide() if self._opacity < 0.02 else None)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setOpacity(self._opacity)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        draw_shadow(p, r, 16, QColor(t.shadow), spread=10, y_offset=5, strength=0.8)
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        c1 = QColor(t.card_top)
        c1.setAlpha(235)
        c2 = QColor(t.card_bottom)
        c2.setAlpha(220)
        grad.setColorAt(0, c1)
        grad.setColorAt(1, c2)
        path = QPainterPath()
        path.addRoundedRect(r, 16, 16)
        p.fillPath(path, grad)
        p.setPen(QPen(t.card_border, 1))
        p.drawPath(path)
        draw_glyph(p, "check", QRectF(22, 14, 18, 18), t.mint, 1.9)
        p.setFont(app_font(13, QFont.Weight.DemiBold))
        p.setPen(t.text)
        p.drawText(QRectF(50, 0, self.width() - 66, self.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.message)


class SkeletonBlock(QWidget):
    """加载骨架块，带缓慢流光。"""

    def __init__(self, width: int = 160, height: int = 14, radius: int = 7,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.setFixedSize(width, height)
        self.radius = radius
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)
        self.tm.changed.connect(self.update)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.018) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        base = QColor(255, 255, 255, 24 if t.is_dark else 120)
        p.setBrush(base)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        shine = QLinearGradient(0, 0, self.width(), 0)
        pos = -0.4 + self._phase * 1.8
        shine.setColorAt(max(0, pos - 0.2), QColor(255, 255, 255, 0))
        shine.setColorAt(max(0, min(1, pos)), QColor(255, 255, 255, 45 if t.is_dark else 90))
        shine.setColorAt(min(1, pos + 0.2), QColor(255, 255, 255, 0))
        p.setBrush(shine)
        p.drawRoundedRect(QRectF(self.rect()), self.radius, self.radius)


class EmptyState(QWidget):
    """空状态：柔和插画 + 主文案 + 次级说明。"""

    def __init__(self, icon: str, title: str, subtitle: str,
                 action_text: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.icon = icon
        self.title = title
        self.subtitle = subtitle
        self.action_text = action_text
        self.setMinimumHeight(270)
        self.tm.changed.connect(self.update)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = self.width() / 2
        # 插画光晕
        rad = 96
        gradient = QRadialGradient(cx, 88, rad)
        gradient.setColorAt(0, QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 45))
        gradient.setColorAt(0.6, QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 14))
        gradient.setColorAt(1, QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 0))
        p.fillRect(QRectF(cx - rad, 88 - rad, rad * 2, rad * 2), gradient)
        # 圆形底盘
        p.setBrush(QColor(255, 255, 255, 18 if t.is_dark else 100))
        p.setPen(QPen(QColor(255, 255, 255, 45 if t.is_dark else 160), 1))
        p.drawEllipse(QPointF(cx, 88), 43, 43)
        draw_glyph(p, self.icon, QRectF(cx - 22, 66, 44, 44), t.accent, 1.4)
        p.setFont(app_font(18, QFont.Weight.DemiBold))
        p.setPen(t.text)
        p.drawText(QRectF(0, 148, self.width(), 30),
                   int(Qt.AlignmentFlag.AlignHCenter), self.title)
        p.setFont(app_font(12))
        p.setPen(t.muted)
        p.drawText(QRectF(24, 180, self.width() - 48, 52),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap), self.subtitle)


class Separator(QWidget):
    def __init__(self, parent: Optional[QWidget] = None, horizontal: bool = True) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        if horizontal:
            self.setFixedHeight(1)
        else:
            self.setFixedWidth(1)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), self.tm.theme.divider)
