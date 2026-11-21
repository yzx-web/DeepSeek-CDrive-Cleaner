# -*- coding: utf-8 -*-
"""左侧 240px 玻璃边栏：品牌区 + 五个导航项 + 本地账户区。"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import (Property, QEasingCurve, QPoint, QPointF, QPropertyAnimation,
                            QRect, QRectF, QSize, Qt, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from ui.glass import (GlassButton, GlassCard, IconButton, Label, Separator, draw_glass,
                      draw_shadow, format_size)
from ui.icons import Glyph, LogoMark, draw_glyph
from ui.theme import RADIUS, SPACE, ThemeManager, app_font, tint
from scanner import DiskStats, get_disk_stats


NAV_ITEMS = [
    ("dashboard", "dashboard", "仪表盘"),
    ("cleaner", "clean", "垃圾清理"),
    ("files", "search", "大文件体检"),
    ("history", "history", "清理记录"),
    ("settings", "settings", "设置"),
]


class NavIndicator(QWidget):
    """被选中项的滑动胶囊，带玻璃高光。"""

    def __init__(self, parent: QWidget, theme_manager: ThemeManager) -> None:
        super().__init__(parent)
        self.tm = theme_manager
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(0, 0, 1, 1)
        self.tm.changed.connect(self.update)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 13, 13)
        if t.is_dark:
            grad = QLinearGradient(r.topLeft(), r.bottomRight())
            grad.setColorAt(0, QColor("#8C79FF"))
            grad.setColorAt(1, QColor("#B75AF3"))
            p.fillPath(path, grad)
            p.save()
            p.setClipPath(path)
            gloss = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
            gloss.setColorAt(0, QColor(255, 255, 255, 72))
            gloss.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(r, gloss)
            p.restore()
            p.setPen(QPen(QColor(255, 255, 255, 120), 1))
        else:
            p.fillPath(path, QColor(255, 255, 255, 234))
            p.save()
            p.setClipPath(path)
            gloss = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
            gloss.setColorAt(0, QColor(255, 255, 255, 255))
            gloss.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(r, gloss)
            p.restore()
            p.setPen(QPen(QColor(255, 255, 255, 255), 1))
        p.drawPath(path)
        # 底部厚度阴影
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 12, 40, 24))
        p.drawRoundedRect(QRectF(r.left() + 5, r.bottom() - 2, r.width() - 10, 2), 2, 2)


class NavItem(QAbstractButton):
    def __init__(self, key: str, icon: str, label: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.key = key
        self.icon = icon
        self.label = label
        self._selected = False
        self._hover = 0.0
        self.setFixedHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(label)
        self._anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.tm.changed.connect(self.update)

    def set_selected(self, value: bool) -> None:
        self._selected = value
        self.update()

    def get_hover(self) -> float:
        return self._hover

    def set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hoverProgress = Property(float, get_hover, set_hover)

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

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(208, 46)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if not self._selected and self._hover > 0:
            c = QColor(255, 255, 255, int((20 if t.is_dark else 70) * self._hover))
            p.setBrush(c)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(r, 13, 13)
        color = QColor("#FFFFFF") if (self._selected and t.is_dark) else t.subtext
        if self._selected and not t.is_dark:
            color = t.accent
        if self._selected and t.is_dark:
            color = QColor("#FFFFFF")
        icon_color = color
        draw_glyph(p, self.icon, QRectF(18, (self.height() - 19) / 2, 19, 19),
                   icon_color, 1.65)
        p.setFont(app_font(13, QFont.Weight.DemiBold if self._selected else QFont.Weight.Medium))
        p.setPen(color)
        p.drawText(QRectF(48, 0, self.width() - 60, self.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.label)
        if self._selected:
            p.setBrush(QColor(255, 255, 255, 90) if t.is_dark else QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 110))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(self.width() - 23, self.height() / 2 - 2.5, 5, 5))


class SpaceMeter(QWidget):
    """侧栏里的 6px 空间占用条，颜色随健康度变化。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.ratio = 0.0
        self.setFixedHeight(6)
        self.tm.changed.connect(self.update)

    def set_ratio(self, ratio: float) -> None:
        self.ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0, 0, 0, 0)
        p.setBrush(QColor(255, 255, 255, 34 if t.is_dark else 95))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 3, 3)
        if self.ratio <= 0:
            return
        color = t.accent
        if self.ratio >= 0.9:
            color = t.coral
        elif self.ratio >= 0.78:
            color = t.orange
        elif self.ratio < 0.62:
            color = t.mint
        fill = QRectF(r.left(), r.top(), max(6, r.width() * self.ratio), r.height())
        grad = QLinearGradient(fill.topLeft(), fill.topRight())
        grad.setColorAt(0, color.lighter(112))
        grad.setColorAt(1, color)
        p.setBrush(grad)
        p.drawRoundedRect(fill, 3, 3)


class SidebarSpaceCard(GlassCard):
    """C 盘空间概览：让侧栏空白变成实时信息。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, radius=14, padding=11, shadow=False, glow=False)
        self.tm = ThemeManager.instance()
        self.setFixedHeight(86)
        self.layout_.setSpacing(4)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        icon = Glyph("disk", QColor(self.tm.theme.cyan), 14, 1.4, self)
        top.addWidget(icon)
        top.addWidget(Label("C 盘空间", 10, QFont.Weight.DemiBold, parent=self))
        top.addStretch(1)
        self.state = Label("读取中", 9, QFont.Weight.DemiBold, color=self.tm.theme.faint,
                           parent=self)
        top.addWidget(self.state)
        self.layout_.addLayout(top)
        self.meter = SpaceMeter(self)
        self.layout_.addWidget(self.meter)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(4)
        self.percent = Label("—", 9, QFont.Weight.DemiBold, parent=self, numeric=True,
                             color=self.tm.theme.subtext)
        bottom.addWidget(self.percent)
        bottom.addStretch(1)
        self.free = Label("等待读取", 8, QFont.Weight.Normal, color=self.tm.theme.faint,
                          parent=self)
        bottom.addWidget(self.free)
        self.layout_.addLayout(bottom)
        self.set_stats(get_disk_stats())
        self.tm.changed.connect(self._sync_theme)

    def _sync_theme(self, *_args) -> None:
        self.meter.update()
        if hasattr(self, "_disk"):
            self.set_stats(self._disk)
        else:
            self._paint_texts()

    def set_stats(self, disk: DiskStats) -> None:
        self._disk = disk
        if not disk.total:
            self.meter.set_ratio(0)
            self.percent.setText("—")
            self.free.setText("等待读取")
            self.state.setText("读取中")
            self._state_color = self.tm.theme.faint
            self._paint_texts()
            return
        ratio = disk.used / disk.total
        self.meter.set_ratio(ratio)
        self.percent.setText(f"{ratio * 100:.0f}% 已用")
        self.free.setText(f"可用 {format_size(disk.free)}")
        if ratio >= 0.9:
            self.state.setText("偏满")
            self._state_color = self.tm.theme.coral
        elif ratio >= 0.78:
            self.state.setText("偏重")
            self._state_color = self.tm.theme.orange
        else:
            self.state.setText("良好")
            self._state_color = self.tm.theme.mint
        self._paint_texts()

    def _paint_texts(self) -> None:
        color = getattr(self, "_state_color", self.tm.theme.faint)
        self.state.setStyleSheet(f"color: {color.name()}; background: transparent;")
        self.percent.setStyleSheet(f"color: {self.tm.theme.subtext.name()}; background: transparent;")
        self.free.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")


class Sidebar(QWidget):
    nav_changed = Signal(str)
    quit_requested = Signal()
    scan_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.setFixedWidth(240)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._selected = "dashboard"
        self._buttons: Dict[str, NavItem] = {}
        self._indicator: Optional[NavIndicator] = None
        self._indicator_anim: Optional[QPropertyAnimation] = None
        self._build()
        self._apply_theme()
        self.tm.changed.connect(self.update)
        self.tm.changed.connect(self._apply_theme)

    def _apply_theme(self, *_args) -> None:
        t = self.tm.theme
        if t.is_dark:
            self.version_label.setStyleSheet(
                "color: rgba(255,255,255,180); background: rgba(255,255,255,38);"
                "border: 1px solid rgba(255,255,255,52); border-radius: 5px; padding: 1px 5px;")
        else:
            self.version_label.setStyleSheet(
                f"color: {t.accent.name()}; background: rgba(94,92,230,24);"
                "border: 1px solid rgba(94,92,230,60); border-radius: 5px; padding: 1px 5px;")

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 14, 12, 12)
        root.setSpacing(0)

        # 品牌区
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 2, 4, 0)
        brand.setSpacing(10)
        logo = LogoMark(42)
        brand.addWidget(logo)
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        title = Label("DeepSeek", 17, QFont.Weight.Bold, parent=self, display=True)
        title.setStyleSheet(title.styleSheet() + "letter-spacing: 0.3px;")
        subtitle = Label("C盘清理专家", 10, QFont.Weight.DemiBold,
                         color=self.tm.theme.muted, parent=self)
        text_col.addWidget(title)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        row.addWidget(subtitle)
        self.version_label = QLabel("4.1", self)
        self.version_label.setFont(app_font(9, QFont.Weight.Bold, numeric=True))
        row.addWidget(self.version_label)
        row.addStretch(1)
        text_col.addLayout(row)
        brand.addLayout(text_col, 1)
        root.addLayout(brand)
        root.addSpacing(16)

        # “本地安全”小胶囊
        safe = QWidget(self)
        safe.setFixedHeight(30)
        safe_layout = QHBoxLayout(safe)
        safe_layout.setContentsMargins(10, 0, 10, 0)
        safe_layout.setSpacing(6)
        shield = Glyph("shield", QColor(self.tm.theme.mint), 14, 1.4, safe)
        safe_layout.addWidget(shield)
        safe_text = Label("本地处理 · 数据不上传", 10, QFont.Weight.Medium,
                          color=self.tm.theme.muted, parent=safe)
        safe_layout.addWidget(safe_text)
        safe.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        safe._bg = True  # type: ignore[attr-defined]
        safe.paintEvent = lambda ev, w=safe: _paint_safe(w, self.tm)  # type: ignore[assignment]
        root.addWidget(safe)
        root.addSpacing(20)

        section = QLabel("工作台", self)
        section.setFont(app_font(10, QFont.Weight.DemiBold))
        section.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;"
                              "letter-spacing: 1.2px; padding-left: 10px;")
        root.addWidget(section)
        root.addSpacing(8)

        # 导航
        nav_host = QWidget(self)
        nav_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(4)
        self._indicator = NavIndicator(nav_host, self.tm)
        self._indicator.hide()
        for key, icon, label in NAV_ITEMS:
            item = NavItem(key, icon, label, nav_host)
            item.clicked.connect(lambda _checked=False, k=key: self.select(k, emit=True))
            self._buttons[key] = item
            nav_layout.addWidget(item)
        root.addWidget(nav_host)
        root.addSpacing(14)

        # 快速扫描：把侧栏的空白变成可用的动作
        self.quick_scan = GlassButton("快速扫描", "primary", "sparkles", self, height=44)
        self.quick_scan.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.quick_scan.clicked.connect(self.scan_requested)
        root.addWidget(self.quick_scan)
        root.addSpacing(10)

        self.space_card = SidebarSpaceCard(self)
        root.addWidget(self.space_card)
        root.addSpacing(10)
        root.addStretch(1)

        # 小卡片：本周护理提醒
        care = GlassCard(self, radius=14, padding=13, shadow=False, glow=False)
        care.setFixedHeight(88)
        care.layout_.setSpacing(4)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        glyph = Glyph("sparkles", QColor(self.tm.theme.accent_alt), 15, 1.4, care)
        top.addWidget(glyph)
        top.addWidget(Label("每周护理", 11, QFont.Weight.DemiBold, parent=care))
        top.addStretch(1)
        top.addWidget(Label("周日", 10, QFont.Weight.Medium, self.tm.theme.muted, care))
        care.layout_.addLayout(top)
        care.layout_.addWidget(Label("给 C 盘一次轻盈呼吸，\n顺便看看大文件。", 10,
                                     QFont.Weight.Normal, self.tm.theme.muted, care))
        root.addWidget(care)
        root.addSpacing(12)

        # 账户区
        account = QWidget(self)
        account.setFixedHeight(58)
        account.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        al = QHBoxLayout(account)
        al.setContentsMargins(8, 8, 6, 8)
        al.setSpacing(9)
        avatar = QLabel("D", account)
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFont(app_font(15, QFont.Weight.Bold))
        avatar.setStyleSheet("color: white; border-radius: 16px;"
                             "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                             "stop:0 #7F7AFF, stop:1 #C061FF);"
                             "border: 1px solid rgba(255,255,255,150);")
        al.addWidget(avatar)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(Label("DeepSeek 用户", 11, QFont.Weight.DemiBold, parent=account))
        col.addWidget(Label("本地账户 · 安全模式", 9, QFont.Weight.Normal,
                            self.tm.theme.muted, account))
        al.addLayout(col, 1)
        power = IconButton("power", 28, danger=False, parent=account, tooltip="退出软件")
        power.clicked.connect(self.quit_requested)
        al.addWidget(power)
        account._bg = True  # type: ignore[attr-defined]
        account.paintEvent = lambda ev, w=account: _paint_account(w, self.tm)  # type: ignore[assignment]
        root.addWidget(account)

        self.select("dashboard", emit=False, animate=False)

    def select(self, key: str, emit: bool = True, animate: bool = True) -> None:
        if key not in self._buttons:
            return
        changed = key != self._selected
        self._selected = key
        for k, button in self._buttons.items():
            button.set_selected(k == key)
        target = self._buttons[key]
        if self._indicator is not None:
            # 把按钮坐标映射到 indicator 的父控件
            top_left = target.mapTo(self._indicator.parentWidget(), QPoint(0, 0))
            geo = QRect(top_left.x(), top_left.y(), target.width(), target.height())
            self._indicator.show()
            self._indicator.lower()
            if not animate or self._indicator.width() <= 1:
                self._indicator.setGeometry(geo)
            else:
                anim = QPropertyAnimation(self._indicator, b"geometry", self)
                anim.setDuration(200)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim.setStartValue(self._indicator.geometry())
                anim.setEndValue(geo)
                anim.start()
                self._indicator_anim = anim  # keep ref
        if emit and changed:
            self.nav_changed.emit(key)

    def current_key(self) -> str:
        return self._selected

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._indicator is not None and self._selected in self._buttons:
            target = self._buttons[self._selected]
            top_left = target.mapTo(self._indicator.parentWidget(), QPoint(0, 0))
            self._indicator.setGeometry(top_left.x(), top_left.y(), target.width(), target.height())

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        draw_shadow(p, r, 18, QColor(t.shadow), spread=12, y_offset=6, strength=0.55)
        draw_glass(p, r, t, 18, alpha_boost=22, glow=False)
        # 边栏右缘顶部有极淡高光
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor(255, 255, 255, 70 if t.is_dark else 140))
        grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(QPen(grad, 1))
        p.drawLine(self.width() - 8, 26, self.width() - 8, self.height() - 26)


def _paint_safe(widget: QWidget, tm: ThemeManager) -> None:
    t = tm.theme
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    r = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    p.setBrush(QColor(255, 255, 255, 20 if t.is_dark else 80))
    p.setPen(QPen(QColor(255, 255, 255, 45 if t.is_dark else 130), 1))
    p.drawRoundedRect(r, 9, 9)


def _paint_account(widget: QWidget, tm: ThemeManager) -> None:
    t = tm.theme
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    r = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    draw_glass(p, r, t, 13, alpha_boost=10)
