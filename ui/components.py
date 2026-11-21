# -*- coding: utf-8 -*-
"""跨页面复用的信息组件：页头、状态胶囊、迷你数据卡、分段控件、圆形勾选框等。"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import (Property, QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect,
                            QRectF, QSize, Qt, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from .glass import GlassCard, Label, draw_glass, draw_shadow
from .icons import Glyph, draw_glyph
from .theme import RADIUS, SPACE, ThemeManager, app_font, tint


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", eyebrow: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(4)
        self.eyebrow_label: Optional[QLabel] = None
        self.eyebrow_rule: Optional[QLabel] = None
        if eyebrow:
            eyebrow_row = QHBoxLayout()
            eyebrow_row.setContentsMargins(0, 0, 0, 0)
            eyebrow_row.setSpacing(7)
            self.eyebrow_rule = QLabel(self)
            self.eyebrow_rule.setFixedSize(18, 2)
            eyebrow_row.addWidget(self.eyebrow_rule)
            self.eyebrow_label = QLabel(eyebrow.upper(), self)
            self.eyebrow_label.setFont(app_font(9, QFont.Weight.Bold))
            self.eyebrow_label.setStyleSheet("background: transparent; letter-spacing: 1.7px;")
            eyebrow_row.addWidget(self.eyebrow_label)
            eyebrow_row.addStretch(1)
            left.addLayout(eyebrow_row)
            self.tm.changed.connect(self._sync_eyebrow)
            self._sync_eyebrow()
        self.title = Label(title, 28, QFont.Weight.Bold, parent=self, display=True)
        self.title.setStyleSheet(self.title.styleSheet() + "letter-spacing: -0.4px;")
        left.addWidget(self.title)
        self.subtitle = Label(subtitle, 12, QFont.Weight.Normal,
                              color=self.tm.theme.muted, parent=self)
        self.subtitle.setMaximumWidth(820)
        left.addWidget(self.subtitle)
        root.addLayout(left, 1)
        self.right = QHBoxLayout()
        self.right.setContentsMargins(0, 0, 0, 0)
        self.right.setSpacing(8)
        self.right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        root.addLayout(self.right)

    def _sync_eyebrow(self, *_args) -> None:
        accent = self.tm.theme.accent
        if self.eyebrow_rule is not None:
            self.eyebrow_rule.setStyleSheet(
                f"background: rgba({accent.red()},{accent.green()},{accent.blue()},190);"
                "border-radius: 1px;")
        if self.eyebrow_label is not None:
            self.eyebrow_label.setStyleSheet(
                f"color: {accent.name()}; background: transparent; letter-spacing: 1.7px;")

    def set_eyebrow(self, text: str) -> None:
        if self.eyebrow_label is not None:
            self.eyebrow_label.setText(text.upper())

    def set_texts(self, title: str, subtitle: str) -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)

    def add_right(self, widget: QWidget) -> None:
        self.right.addWidget(widget)


class StatusPill(QWidget):
    """带呼吸小点的状态胶囊。"""

    def __init__(self, text: str, color: Optional[QColor] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.text_value = text
        self.color = QColor(color) if color else QColor(self.tm.theme.mint)
        self.setFont(app_font(11, QFont.Weight.DemiBold))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.tm.changed.connect(self.update)

    def set_text(self, text: str, color: Optional[QColor] = None) -> None:
        self.text_value = text
        if color is not None:
            self.color = QColor(color)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text_value) + 38, 30)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(255, 255, 255, 25 if t.is_dark else 110))
        p.setPen(QPen(QColor(255, 255, 255, 52 if t.is_dark else 175), 1))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        c = QColor(self.color)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 32))
        p.drawEllipse(QRectF(13, r.center().y() - 6, 12, 12))
        p.setBrush(c)
        p.drawEllipse(QRectF(17, r.center().y() - 2, 4, 4))
        p.setFont(self.font())
        p.setPen(t.text)
        p.drawText(QRectF(30, 0, r.width() - 36, r.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.text_value)
        # 顶部高光
        gloss = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + r.height() / 2))
        gloss.setColorAt(0, QColor(255, 255, 255, 38))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(gloss)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(r.left() + 6, r.top() + 1, r.width() - 12, r.height() / 2 - 1),
                          r.height() / 2, r.height() / 2)


class MiniStatCard(GlassCard):
    """三个横向小玻璃卡片之一：已用 / 可释放 / 上次清理。"""

    def __init__(self, title: str, value: str, hint: str, color: QColor,
                 icon: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, radius=13, padding=12, shadow=False)
        self.layout_.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        if icon:
            top.addWidget(Glyph(icon, color, 13, 1.5, self))
        cap = Label(title, 10, QFont.Weight.Medium, color=self.tm.theme.muted, parent=self)
        top.addWidget(cap)
        top.addStretch(1)
        self.layout_.addLayout(top)
        self.value_label = Label(value, 20, QFont.Weight.Bold, parent=self, display=True,
                                 line_height=1.15)
        self.value_label.setStyleSheet(self.value_label.styleSheet() +
                                       "letter-spacing: -0.3px;")
        self.layout_.addWidget(self.value_label)
        self.hint_label = Label(hint, 9, QFont.Weight.Normal, color=self.tm.theme.faint,
                                parent=self, line_height=1.2)
        self.layout_.addWidget(self.hint_label)
        self.setMinimumHeight(88)

    def set_value(self, value: str, hint: Optional[str] = None) -> None:
        self.value_label.setText(value)
        if hint is not None:
            self.hint_label.setText(hint)


class SegmentedControl(QWidget):
    """iOS 分段控件：选中项为滑动白色/紫色胶囊。"""

    changed = Signal(str)

    def __init__(self, options: List[Tuple[str, str]], current: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.options = options
        self.current = current
        self._index = max(0, [o[0] for o in options].index(current)) if options else 0
        self._pos = float(self._index)
        self._anim = QPropertyAnimation(self, b"pillPos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setFixedHeight(38)
        self.setMinimumWidth(260)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tm.changed.connect(self.update)

    def get_pos(self) -> float:
        return self._pos

    def set_pos(self, value: float) -> None:
        self._pos = value
        self.update()

    pillPos = Property(float, get_pos, set_pos)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(app_font(12, QFont.Weight.DemiBold))
        return QSize(sum(fm.horizontalAdvance(o[1]) + 32 for o in self.options) + 8, 38)

    def set_current(self, value: str) -> None:
        if value not in [o[0] for o in self.options] or value == self.current:
            return
        idx = [o[0] for o in self.options].index(value)
        self.current = value
        self._index = idx
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(idx))
        self._anim.start()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self.options:
            return
        x = event.position().x() - 4
        width = (self.width() - 8) / len(self.options)
        idx = max(0, min(len(self.options) - 1, int(x / width)))
        new_value = self.options[idx][0]
        if new_value != self.current:
            self.set_current(new_value)
            self.changed.emit(new_value)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(255, 255, 255, 19 if t.is_dark else 92))
        p.setPen(QPen(QColor(255, 255, 255, 38 if t.is_dark else 155), 1))
        p.drawRoundedRect(r, 11, 11)
        count = max(1, len(self.options))
        width = (r.width() - 6) / count
        pill = QRectF(r.left() + 3 + width * self._pos, r.top() + 3,
                      width, r.height() - 6)
        p.save()
        path = QPainterPath()
        path.addRoundedRect(pill, 9, 9)
        if t.is_dark:
            grad = QLinearGradient(pill.topLeft(), pill.bottomRight())
            grad.setColorAt(0, QColor("#8A79FF"))
            grad.setColorAt(1, QColor("#B961F0"))
            p.fillPath(path, grad)
        else:
            grad = QLinearGradient(pill.topLeft(), pill.bottomLeft())
            grad.setColorAt(0, QColor("#FFFFFF"))
            grad.setColorAt(1, QColor("#F4F1FF"))
            p.fillPath(path, grad)
        p.setClipPath(path)
        gloss = QLinearGradient(pill.topLeft(), QPointF(pill.left(), pill.center().y()))
        gloss.setColorAt(0, QColor(255, 255, 255, 110 if t.is_dark else 255))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(pill, gloss)
        p.restore()
        for i, (key, label) in enumerate(self.options):
            rect = QRectF(r.left() + 3 + width * i, r.top() + 3, width, r.height() - 6)
            active = i == self._index
            color = (QColor("#FFFFFF") if t.is_dark else t.accent) if active else t.subtext
            p.setFont(app_font(12, QFont.Weight.DemiBold if active else QFont.Weight.Medium))
            p.setPen(color)
            p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), label)


class RoundCheck(QAbstractButton):
    """22px 圆形勾选，勾选时图标块变紫。"""

    def __init__(self, checked: bool = True, color: Optional[QColor] = None,
                 parent: Optional[QWidget] = None, size: int = 22) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.checked_color = QColor(color) if color else QColor(self.tm.theme.accent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._progress = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"checkProgress", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.toggled.connect(self._on_toggle)
        self.tm.changed.connect(self.update)

    def get_progress(self) -> float:
        return self._progress

    def set_progress(self, value: float) -> None:
        self._progress = value
        self.update()

    checkProgress = Property(float, get_progress, set_progress)

    def _on_toggle(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def hitButton(self, pos: QPoint) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setBrush(QColor(255, 255, 255, 20 if t.is_dark else 115))
        p.setPen(QPen(QColor(255, 255, 255, 58 if t.is_dark else 160), 1))
        p.drawEllipse(r)
        if self._progress > 0.01:
            p.setPen(Qt.PenStyle.NoPen)
            c = QColor(self.checked_color)
            p.setBrush(c)
            p.setOpacity(min(1.0, self._progress * 1.4))
            p.drawEllipse(r.adjusted(1, 1, -1, -1))
            p.setOpacity(1)
            # 勾
            p.setPen(QPen(QColor(255, 255, 255), 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(6.2, self.height() / 2 + 0.4)
            path.lineTo(9.6, self.height() / 2 + 3.6)
            path.lineTo(self.width() - 5.8, self.height() / 2 - 4.0)
            p.drawPath(path)
        # 顶部高光
        gloss = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
        gloss.setColorAt(0, QColor(255, 255, 255, 42))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(gloss)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(r.adjusted(3, 2, -3, -r.height() / 2))


class Tag(QWidget):
    def __init__(self, text: str, color: QColor, parent: Optional[QWidget] = None,
                 icon: Optional[str] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.text_value = text
        self.color = QColor(color)
        self.icon = icon
        self.setFont(app_font(10, QFont.Weight.DemiBold))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text_value) + (34 if self.icon else 22), 24)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        c = QColor(self.color)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 30))
        p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 58), 1))
        p.drawRoundedRect(r, 7, 7)
        x = 9
        if self.icon:
            draw_glyph(p, self.icon, QRectF(8, 4, 16, 16), c, 1.4)
            x = 27
        p.setFont(self.font())
        p.setPen(c)
        p.drawText(QRectF(x, 0, r.width() - x - 6, r.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.text_value)


class AlertBanner(GlassCard):
    """权限不足提示：引导以管理员身份运行，并附复制命令按钮。"""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, radius=13, padding=12, shadow=False)
        self.tm = ThemeManager.instance()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(Glyph("warning", QColor(self.tm.theme.orange), 18, 1.5, self))
        self.label = Label(text, 11, QFont.Weight.Medium, color=self.tm.theme.subtext,
                           parent=self, line_height=1.35)
        row.addWidget(self.label, 1)
        self.copy_btn = QLabel("复制启动命令", self)
        self.copy_btn.setFont(app_font(10, QFont.Weight.DemiBold))
        self.copy_btn.setStyleSheet(
            f"color: {self.tm.theme.orange.name()}; background: rgba(255,159,10,28);"
            "border: 1px solid rgba(255,159,10,85); border-radius: 7px; padding: 4px 9px;")
        row.addWidget(self.copy_btn)
        self.layout_.addLayout(row)
        self.setStyleSheet("")


class ReportBars(QWidget):
    """分类色条图：用颜色与长度讲述“空间去哪儿了”。"""

    def __init__(self, data: List[Tuple[str, str, int, QColor]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.data = data
        self.setMinimumHeight(max(80, 30 * len(data)))
        self.tm.changed.connect(self.update)

    def set_data(self, data: List[Tuple[str, str, int, QColor]]) -> None:
        self.data = data
        self.setMinimumHeight(max(80, 30 * len(data)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self.data:
            return
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        total = max(1, sum(d[2] for d in self.data))
        row_h = 27
        for i, (name, icon, value, color) in enumerate(self.data):
            y = i * row_h
            draw_glyph(p, icon, QRectF(0, y + 4, 16, 16), color, 1.3)
            p.setFont(app_font(10, QFont.Weight.Medium))
            p.setPen(t.subtext)
            p.drawText(QRectF(22, y, 100, 22), int(Qt.AlignmentFlag.AlignVCenter), name)
            p.setFont(app_font(10, QFont.Weight.DemiBold, numeric=True))
            p.setPen(t.text)
            p.drawText(QRectF(self.width() - 95, y, 88, 22),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                       self._fmt(value))
            track = QRectF(130, y + 8, max(30, self.width() - 235), 6)
            p.setBrush(QColor(255, 255, 255, 20 if t.is_dark else 75))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(track, 3, 3)
            fill = QRectF(track.left(), track.top(), max(6, track.width() * value / total), 6)
            p.setBrush(color)
            p.drawRoundedRect(fill, 3, 3)

    @staticmethod
    def _fmt(value: int) -> str:
        from .glass import format_size
        return format_size(value)
