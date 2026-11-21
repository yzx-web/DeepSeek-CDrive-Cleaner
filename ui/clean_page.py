# -*- coding: utf-8 -*-
"""垃圾清理页：扫描前、扫描中、结果清单、清理摘要四种完整状态。"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt,
                            Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QScrollArea,
                               QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

from cleaner import CleanResult
from scanner import CATEGORY_MAP, CATEGORIES, CategoryResult, ScanResult
from ui.components import (PageHeader, ReportBars, RoundCheck, StatusPill, Tag)
from ui.glass import (EmptyState, GlassButton, GlassCard, Label, ProgressRing,
                      SkeletonBlock, format_size)
from ui.icons import Glyph, draw_glyph
from ui.theme import ThemeManager, app_font, category_color, tint


class CategoryIconBlock(QWidget):
    def __init__(self, icon: str, color: QColor, parent: Optional[QWidget] = None,
                 size: int = 42) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.icon = icon
        self.color = QColor(color)
        self.selected = False
        self.setFixedSize(size, size)

    def set_selected(self, value: bool) -> None:
        self.selected = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(1, 1, self.width() - 2, self.height() - 3)
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        c = QColor(self.color)
        glyph_color = QColor("#FFFFFF")
        if self.selected:
            c1 = QColor(c).lighter(114 if t.is_dark else 111)
            c2 = QColor(c).darker(124 if t.is_dark else 116)
            grad = QLinearGradient(r.topLeft(), r.bottomRight())
            grad.setColorAt(0, c1)
            grad.setColorAt(1, c2)
            p.fillPath(path, grad)
            glow = QColor(c)
            glow.setAlpha(82 if t.is_dark else 50)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QRectF(r.left() + 3, r.bottom() - 11, r.width() - 6, 20))
        else:
            p.fillPath(path, QColor(c.red(), c.green(), c.blue(), 34 if t.is_dark else 24))
            p.setBrush(QColor(255, 255, 255, 22 if t.is_dark else 60))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(r.right() - 20, r.top() - 4, 28, 28))
            glyph_color = c
        # 高光与描边
        p.save()
        p.setClipPath(path)
        gloss = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
        gloss.setColorAt(0, QColor(255, 255, 255, 68 if self.selected else 30))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, gloss)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 92 if self.selected else 45), 1))
        p.drawPath(path)
        box = 22 if self.width() >= 46 else 19
        draw_glyph(p, self.icon,
                   QRectF((self.width() - box) / 2, (self.height() - box) / 2, box, box),
                   glyph_color, 1.55)


class CategoryCard(GlassCard):
    toggled = Signal(str, bool)
    recycle_clicked = Signal()

    def __init__(self, result: CategoryResult, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, radius=16, padding=12, hover=True, shadow=True)
        self.tm = ThemeManager.instance()
        self.result = result
        self.key = result.key
        self.color = category_color(self.tm.theme)[self.key]
        self._selected = result.defn.default_selected and not result.defn.protected
        self.setMinimumHeight(144)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setToolTip(result.defn.tip)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        self.icon_block = CategoryIconBlock(result.defn.icon, self.color, self, 42)
        self.icon_block.set_selected(self._selected)
        top.addWidget(self.icon_block, 0, Qt.AlignmentFlag.AlignTop)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title = Label(result.defn.title, 15, QFont.Weight.DemiBold, parent=self)
        self.title.setWordWrap(False)
        text_col.addWidget(self.title)
        self.meta = Label(f"{self._display_count()} 项 · {format_size(result.total_size)}",
                          10, QFont.Weight.DemiBold, color=self.tm.theme.subtext, parent=self,
                          numeric=True)
        self.meta.setWordWrap(False)
        text_col.addWidget(self.meta)
        top.addLayout(text_col, 1)
        if result.defn.protected:
            self.check = None
            self.protect_tag = Tag("已保护", self.tm.theme.muted, self, "lock")
            top.addWidget(self.protect_tag, 0, Qt.AlignmentFlag.AlignTop)
        else:
            self.check = RoundCheck(self._selected, self.color, self, 20)
            self.check.toggled.connect(self._on_check)
            top.addWidget(self.check, 0, Qt.AlignmentFlag.AlignTop)
        self.layout_.addLayout(top)
        desc = self.result.defn.description
        self.desc = Label(desc, 10, QFont.Weight.Normal, color=self.tm.theme.muted,
                          parent=self, line_height=1.3)
        self.desc.setMaximumHeight(32)
        self.layout_.addWidget(self.desc)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(6)
        if result.defn.protected:
            bottom.addWidget(Label("请在系统中亲自确认", 9, QFont.Weight.Medium,
                                   color=self.tm.theme.faint, parent=self))
        else:
            self.state_tag = Tag("将清理" if self._selected else "保留",
                                 self.color if self._selected else self.tm.theme.muted,
                                 self, "check" if self._selected else None)
            bottom.addWidget(self.state_tag)
        bottom.addStretch(1)
        self.size_badge = Label(format_size(result.total_size), 10, QFont.Weight.DemiBold,
                                color=self.tm.theme.subtext, parent=self)
        bottom.addWidget(self.size_badge)
        self.layout_.addLayout(bottom)
        self.set_selected(self._selected, emit=False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tm.changed.connect(self._sync_theme)

    def _sync_theme(self, *_args) -> None:
        self.color = category_color(self.tm.theme)[self.key]
        self.icon_block.color = QColor(self.color)
        self.icon_block.update()
        if self.check is not None:
            self.check.checked_color = QColor(self.color)
            self.check.update()
        if hasattr(self, "state_tag"):
            self.state_tag.color = self.color if self._selected else self.tm.theme.muted
            self.state_tag.update()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "protect_tag"):
            self.protect_tag.setVisible(self.width() >= 280)

    def _display_count(self) -> int:
        if self.key == "recycle":
            return max(self.result.scanned_count, self.result.count)
        return self.result.count

    def _on_check(self, checked: bool) -> None:
        self.set_selected(checked, emit=True)

    def set_selected(self, selected: bool, emit: bool = False) -> None:
        self._selected = selected
        self.icon_block.set_selected(selected)
        if self.check is not None:
            if self.check.isChecked() != selected:
                self.check.blockSignals(True)
                self.check.setChecked(selected)
                self.check.blockSignals(False)
            self.check.setVisible(True)
        if hasattr(self, "state_tag"):
            self.state_tag.text_value = "将清理" if selected else "保留"
            self.state_tag.color = self.color if selected else self.tm.theme.muted
            self.state_tag.icon = "check" if selected else None
            self.state_tag.updateGeometry()
            self.state_tag.update()
        self.update()
        if emit:
            self.toggled.emit(self.key, selected)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._selected:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            tint_path = QPainterPath()
            tint_path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1),
                                     self.radius, self.radius)
            c = QColor(self.color)
            c.setAlpha(46 if self.tm.theme.is_dark else 24)
            wash = QLinearGradient(self.rect().topLeft(), self.rect().bottomRight())
            wash.setColorAt(0, c)
            fade = QColor(self.color)
            fade.setAlpha(6)
            wash.setColorAt(1, fade)
            p.fillPath(tint_path, wash)
            c.setAlpha(102 if self.tm.theme.is_dark else 82)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(c, 1.25))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1),
                              self.radius, self.radius)

    def is_selected(self) -> bool:
        return self._selected

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            if self.result.defn.protected:
                self.recycle_clicked.emit()
            else:
                self.set_selected(not self._selected, emit=True)
        super().mouseReleaseEvent(event)


class ScanIllustration(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.setFixedSize(260, 178)
        self.tm.changed.connect(self.update)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy = self.width() / 2, 92
        # 光晕
        for radius, alpha in ((92, 35), (70, 24), (48, 17)):
            p.setBrush(QColor(t.accent.red(), t.accent.green(), t.accent.blue(), alpha))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), radius, radius * 0.7)
        # 玻璃圆盘
        p.setBrush(QColor(255, 255, 255, 25 if t.is_dark else 105))
        p.setPen(QPen(QColor(255, 255, 255, 65 if t.is_dark else 180), 1))
        p.drawEllipse(QPointF(cx, cy), 56, 44)
        p.setBrush(QColor(255, 255, 255, 36 if t.is_dark else 130))
        p.drawEllipse(QPointF(cx, cy), 44, 34)
        # 磁盘细节
        p.setBrush(QColor(t.accent))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 18, 14)
        draw_glyph(p, "disk", QRectF(cx - 12, cy - 12, 24, 24), QColor("#FFFFFF"), 1.4)
        # 环绕小光点
        colors = category_color(t)
        points = [(-82, -24, "temp"), (73, -32, "browser"), (-66, 31, "prefetch"), (81, 26, "logs")]
        for dx, dy, key in points:
            c = colors[key]
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 190))
            p.drawEllipse(QPointF(cx + dx, cy + dy), 5, 5)
        # 中心文字
        p.setFont(app_font(10, QFont.Weight.DemiBold))
        p.setPen(QColor(t.muted))
        p.drawText(QRectF(0, 154, self.width(), 20),
                   int(Qt.AlignmentFlag.AlignHCenter), "安全扫描 · 只看不删")


class CleanPage(QWidget):
    scan_requested = Signal()
    cancel_scan_requested = Signal()
    clean_requested = Signal(list)   # list[CategoryResult]
    recycle_open_requested = Signal()
    report_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.scan_result: Optional[ScanResult] = None
        self.category_cards: Dict[str, CategoryCard] = {}
        self.live_rows: Dict[str, Dict[str, QLabel]] = {}
        self._scanning = False
        self._build()
        self.tm.changed.connect(self._theme_changed)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 8, 32, 22)
        root.setSpacing(16)
        self.header = PageHeader("垃圾清理",
                                 "8 个区域逐一检查。你保留决定权，所有删除都会进入回收站。",
                                 eyebrow="SMART CLEAN")
        self.header.add_right(StatusPill("安全模式 · 可撤销", self.tm.theme.mint))
        root.addWidget(self.header)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body_host = QWidget()
        self.body_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.body = QVBoxLayout(self.body_host)
        self.body.setContentsMargins(0, 0, 4, 4)
        self.body.setSpacing(16)
        self.scroll.setWidget(self.body_host)
        root.addWidget(self.scroll, 1)

        self._build_empty()
        self._build_scanning()
        self._build_result()
        self._show_empty()

    def _build_empty(self) -> None:
        self.empty = GlassCard(self, radius=18, padding=26, glow=True)
        self.empty.layout_.setSpacing(8)
        self.empty.layout_.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ill = ScanIllustration(self.empty)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(ill)
        row.addStretch(1)
        self.empty.layout_.addLayout(row)
        title = Label("准备好了吗？", 24, QFont.Weight.Bold, parent=self.empty, display=True)
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.empty.layout_.addWidget(title)
        sub = Label("我们会轻轻翻开 C 盘的 8 个角落，看看哪些东西已经不需要了。\n扫描不会删除任何文件，连一个字节都不会动。",
                    12, QFont.Weight.Normal, color=self.tm.theme.muted, parent=self.empty)
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.empty.layout_.addWidget(sub)
        self.empty.layout_.addSpacing(10)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.start_btn = GlassButton("开始扫描", "primary", "sparkles", self.empty, height=52,
                                     min_width=230)
        self.start_btn.clicked.connect(self.scan_requested)
        btn_row.addWidget(self.start_btn)
        btn_row.addStretch(1)
        self.empty.layout_.addLayout(btn_row)
        self.empty.layout_.addSpacing(6)
        foot = QLabel("通常需要 10–30 秒 · 你可以随时取消", self.empty)
        foot.setFont(app_font(10))
        foot.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        foot.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
        self.empty.layout_.addWidget(foot)

        # 类别预览条
        preview = QHBoxLayout()
        preview.setSpacing(6)
        preview.setContentsMargins(0, 12, 0, 0)
        colors = category_color(self.tm.theme)
        for cat in CATEGORIES:
            c = colors[cat.key]
            box = QWidget(self.empty)
            box.setFixedHeight(30)
            box.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},18);"
                              f"border: 1px solid rgba({c.red()},{c.green()},{c.blue()},42);"
                              "border-radius: 8px;")
            lay = QHBoxLayout(box)
            lay.setContentsMargins(8, 0, 8, 0)
            lay.setSpacing(4)
            gl = Glyph(cat.icon, c, 13, 1.3, box)
            lay.addWidget(gl)
            lbl = QLabel(cat.title, box)
            lbl.setFont(app_font(9))
            lbl.setStyleSheet(f"color: {self.tm.theme.muted.name()}; background: transparent;")
            lay.addWidget(lbl)
            preview.addWidget(box)
        self.empty.layout_.addLayout(preview)
        self.body.addWidget(self.empty)

    def _build_scanning(self) -> None:
        self.scanning = GlassCard(self, radius=18, padding=22, glow=True)
        self.scanning.layout_.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(Label("正在给 C 盘做体检", 20, QFont.Weight.Bold, parent=self.scanning,
                            display=True))
        top.addStretch(1)
        self.scan_status_pill = StatusPill("正在扫描", self.tm.theme.cyan)
        top.addWidget(self.scan_status_pill)
        self.scanning.layout_.addLayout(top)
        self.scanning.layout_.addWidget(Label("先不动任何文件。我们只是轻手轻脚地数一数。",
                                              11, QFont.Weight.Normal,
                                              color=self.tm.theme.muted, parent=self.scanning))
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 6, 0, 0)
        mid.setSpacing(24)
        left = QVBoxLayout()
        self.scan_ring = ProgressRing(222, 15, "0", "%", "已完成", "准备中", self.scanning,
                                      big_size=38)
        lh = QHBoxLayout()
        lh.addStretch(1)
        lh.addWidget(self.scan_ring)
        lh.addStretch(1)
        left.addLayout(lh)
        self.scan_counts = Label("已发现 0 个文件 · 0 B", 11, QFont.Weight.Medium,
                                 color=self.tm.theme.subtext, parent=self.scanning, numeric=True)
        self.scan_counts.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        left.addWidget(self.scan_counts)
        mid.addLayout(left, 4)
        right_col = QVBoxLayout()
        right_col.setSpacing(7)
        colors = category_color(self.tm.theme)
        for cat in CATEGORIES:
            row = QWidget(self.scanning)
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(8)
            icon = QWidget(row)
            icon.setFixedSize(24, 24)
            c = colors[cat.key]
            icon.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},28);"
                               "border-radius: 7px;")
            g = Glyph(cat.icon, c, 13, 1.3, icon)
            g.move(5.5, 5.5)
            rl.addWidget(icon)
            name = QLabel(cat.title, row)
            name.setFont(app_font(10, QFont.Weight.Medium))
            name.setStyleSheet(f"color: {self.tm.theme.subtext.name()}; background: transparent;")
            rl.addWidget(name)
            rl.addStretch(1)
            val = QLabel("等待", row)
            val.setFont(app_font(9, QFont.Weight.Medium, numeric=True))
            val.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
            rl.addWidget(val)
            right_col.addWidget(row)
            self.live_rows[cat.key] = {"name": name, "val": val, "icon": icon}
        mid.addLayout(right_col, 6)
        self.scanning.layout_.addLayout(mid)
        bottom = QHBoxLayout()
        self.scan_current = Label("正在准备扫描任务…", 10, QFont.Weight.Normal,
                                  color=self.tm.theme.muted, parent=self.scanning)
        bottom.addWidget(self.scan_current, 1)
        self.cancel_btn = GlassButton("取消扫描", "secondary", "close", self.scanning,
                                      height=38, min_width=112, compact=True)
        self.cancel_btn.clicked.connect(self.cancel_scan_requested)
        bottom.addWidget(self.cancel_btn)
        self.scanning.layout_.addLayout(bottom)
        self.body.addWidget(self.scanning)

    def _build_result(self) -> None:
        self.result_host = QWidget(self)
        self.result_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.result_host.setMinimumWidth(0)
        self.result_root = QVBoxLayout(self.result_host)
        self.result_root.setContentsMargins(0, 0, 0, 0)
        self.result_root.setSpacing(12)

        # 顶部结果条
        self.banner = GlassCard(self.result_host, radius=14, padding=14, shadow=False)
        self.banner.setMinimumHeight(52)
        bl = QHBoxLayout()
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        bl.addWidget(Glyph("sparkles", QColor(self.tm.theme.accent), 18, 1.5, self.banner))
        self.banner_text = Label("扫描完成，先看看这些“小负担”。", 12, QFont.Weight.Medium,
                                 parent=self.banner)
        bl.addWidget(self.banner_text, 1)
        self.select_all_btn = QLabel("全选", self.banner)
        self.select_all_btn.setFont(app_font(10, QFont.Weight.DemiBold))
        self.select_all_btn.setStyleSheet(f"color: {self.tm.theme.accent.name()};"
                                          "background: transparent; padding: 4px 8px;")
        self.select_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all_btn.mousePressEvent = lambda e: self._toggle_all()  # type: ignore[assignment]
        bl.addWidget(self.select_all_btn)
        self.banner.layout_.addLayout(bl)
        self.result_root.addWidget(self.banner)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(16)
        self.result_root.addLayout(content)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)
        content.addLayout(left, 1)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(10)
        left.addLayout(self.grid)
        left.addStretch(1)

        # 右侧摘要
        self.summary = GlassCard(self.result_host, radius=18, padding=18, glow=True)
        self.summary.setFixedWidth(300)
        self.summary.layout_.setSpacing(8)
        self.summary.layout_.addWidget(Label("准备释放", 11, QFont.Weight.DemiBold,
                                             color=self.tm.theme.muted, parent=self.summary))
        self.summary_number = Label("0 B", 40, QFont.Weight.Bold, parent=self.summary,
                                    display=True, line_height=1.1)
        self.summary_number.setStyleSheet(self.summary_number.styleSheet() + "letter-spacing:-1.2px;")
        self.summary.layout_.addWidget(self.summary_number)
        self.summary_note = Label("勾选你想告别的类别。", 10, QFont.Weight.Normal,
                                  color=self.tm.theme.muted, parent=self.summary)
        self.summary.layout_.addWidget(self.summary_note)
        self.summary.layout_.addSpacing(2)
        self.summary_divider = QWidget(self.summary)
        self.summary_divider.setFixedHeight(1)
        self.summary_divider.setStyleSheet(f"background: {self.tm.theme.divider.name()};")
        self.summary.layout_.addWidget(self.summary_divider)
        self.summary_items = QVBoxLayout()
        self.summary_items.setSpacing(3)
        self.summary.layout_.addLayout(self.summary_items)
        self.summary_sizes = Label("", 10, QFont.Weight.Normal, color=self.tm.theme.faint,
                                   parent=self.summary)
        self.summary.layout_.addWidget(self.summary_sizes)
        self.summary.layout_.addSpacing(4)
        self.clean_btn = GlassButton("立即清理", "cta", "clean", self.summary, height=50)
        self.clean_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.clean_btn.clicked.connect(self._request_clean)
        self.summary.layout_.addWidget(self.clean_btn)
        self.rescan_btn = GlassButton("重新扫描", "secondary", "search", self.summary, height=42)
        self.rescan_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.rescan_btn.clicked.connect(self.scan_requested)
        self.summary.layout_.addWidget(self.rescan_btn)
        self.recycle_btn = GlassButton("打开回收站确认", "ghost", "external", self.summary,
                                       height=34, compact=True)
        self.recycle_btn.clicked.connect(self.recycle_open_requested)
        self.summary.layout_.addWidget(self.recycle_btn)
        self.summary.layout_.addStretch(1)
        self.recycle_hint = Label("回收站类别仅统计，不代你永久清空。",
                                  9, QFont.Weight.Normal, color=self.tm.theme.faint,
                                  parent=self.summary)
        self.summary.layout_.addWidget(self.recycle_hint)
        content.addWidget(self.summary, 0, Qt.AlignmentFlag.AlignTop)
        self.body.addWidget(self.result_host)

    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_width()

    def _apply_responsive_width(self) -> None:
        if not hasattr(self, "summary"):
            return
        self.summary.setFixedWidth(300 if self.width() >= 1000 else 260)

    def _show_empty(self) -> None:
        self.empty.show()
        self.scanning.hide()
        self.result_host.hide()

    def _show_scanning(self) -> None:
        self.empty.hide()
        self.scanning.show()
        self.result_host.hide()
        self.scan_status_pill.set_text("正在扫描", self.tm.theme.cyan)
        self.scan_current.setText("正在准备扫描任务…")
        self.scan_ring.set_value(0.0, "0", "%", "已完成", "准备中", animate=False)
        self.scan_counts.setText("已发现 0 个文件 · 0 B")
        for key, row in self.live_rows.items():
            row["val"].setText("等待")
            row["val"].setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")

    def _show_result(self) -> None:
        self.empty.hide()
        self.scanning.hide()
        self.result_host.show()

    def _theme_changed(self, *_args) -> None:
        self.summary_divider.setStyleSheet(f"background: {self.tm.theme.divider.name()};")

    def begin_scan(self) -> None:
        self._scanning = True
        self._show_scanning()

    def on_scan_overall(self, progress: float, label: str, count: int, size: int) -> None:
        key_name = CATEGORY_MAP[label].title if label in CATEGORY_MAP else label
        self.scan_ring.set_value(progress, f"{progress * 100:.0f}", "%", "已完成", key_name)
        self.scan_counts.setText(f"已发现 {count:,} 个文件 · {format_size(size)}")
        self.scan_current.setText(f"正在检查：{key_name}")

    def on_scan_category_progress(self, key: str, count: int, size: int) -> None:
        if key not in self.live_rows:
            return
        row = self.live_rows[key]
        row["val"].setText(f"{count:,} 项 · {format_size(size)}")
        row["val"].setStyleSheet(f"color: {self.tm.theme.subtext.name()}; background: transparent;")

    def on_scan_category_done(self, result: CategoryResult) -> None:
        if result.key in self.live_rows:
            row = self.live_rows[result.key]
            row["val"].setText(f"完成 · {format_size(result.total_size)}")
            row["val"].setStyleSheet(f"color: {self.tm.theme.mint.name()}; background: transparent;")
            row["name"].setStyleSheet(f"color: {self.tm.theme.text.name()}; background: transparent;")

    def on_scan_finished(self, result: ScanResult) -> None:
        self._scanning = False
        self.set_scan_result(result)

    def set_scan_result(self, result: ScanResult) -> None:
        self.scan_result = result
        # 清空旧卡片
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.category_cards.clear()
        self._show_result()
        self.banner_text.setText(
            f"扫描完成 · {result.total_count:,} 个文件 · 约 {format_size(result.total_size)}，"
            f"用时 {result.elapsed:.1f} 秒。")
        colors = category_color(self.tm.theme)
        selected_count = 0
        selected_size = 0
        for index, cat in enumerate([result.categories.get(c.key) for c in CATEGORIES]):
            if cat is None:
                continue
            card = CategoryCard(cat, self.result_host)
            card.toggled.connect(self._on_card_toggled)
            card.recycle_clicked.connect(self.recycle_open_requested)
            self.grid.addWidget(card, index // 2, index % 2)
            self.category_cards[cat.key] = card
        self._recalc_summary()
        self._refresh_summary_items()
        if result.total_size == 0:
            self._show_healthy_empty()

    def _show_healthy_empty(self) -> None:
        # 所有类别为空：用一个完整的空状态替代网格
        self.banner_text.setText("你的 C 盘很健康，继续保持。")
        self.clean_btn.setEnabled(False)

    def _on_card_toggled(self, key: str, selected: bool) -> None:
        self._recalc_summary()

    def _selected_categories(self) -> List[CategoryResult]:
        if self.scan_result is None:
            return []
        out = []
        for key, card in self.category_cards.items():
            if card.is_selected() and key in self.scan_result.categories:
                cat = self.scan_result.categories[key]
                if cat.defn.protected or cat.count == 0:
                    continue
                out.append(cat)
        return out

    def _recalc_summary(self) -> None:
        selected = self._selected_categories()
        size = sum(c.total_size for c in selected)
        count = sum(c.count for c in selected)
        self.summary_number.setText(format_size(size))
        if size > 0:
            self.summary_note.setText(f"共 {count:,} 个文件，将全部进入回收站。")
        else:
            self.summary_note.setText("还没有勾选可清理的类别。")
        self.clean_btn.setEnabled(size > 0)
        self.clean_btn.setText("立即清理" if size else "暂无可清理内容")
        self._refresh_summary_items()
        self.banner_text.setText(
            f"扫描完成 · 已选 {count:,} 项 · 可释放 {format_size(size)}，"
            "所有文件都会进入回收站。")

    def _refresh_summary_items(self) -> None:
        while self.summary_items.count():
            item = self.summary_items.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        colors = category_color(self.tm.theme)
        selected = self._selected_categories()
        if not selected:
            lab = QLabel("暂无待清理项目", self.summary)
            lab.setFont(app_font(10))
            lab.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
            self.summary_items.addWidget(lab)
            return
        for cat in sorted(selected, key=lambda c: c.total_size, reverse=True)[:5]:
            row = QWidget(self.summary)
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 1, 0, 1)
            rl.setSpacing(6)
            c = colors[cat.key]
            dot = QWidget(row)
            dot.setFixedSize(7, 7)
            dot.setStyleSheet(f"background: {c.name()}; border-radius: 3px;")
            rl.addWidget(dot)
            name = QLabel(cat.defn.title, row)
            name.setFont(app_font(9))
            name.setStyleSheet(f"color: {self.tm.theme.subtext.name()}; background: transparent;")
            rl.addWidget(name, 1)
            amount = QLabel(format_size(cat.total_size), row)
            amount.setFont(app_font(9, QFont.Weight.DemiBold, numeric=True))
            amount.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
            rl.addWidget(amount)
            self.summary_items.addWidget(row)
        if len(selected) > 5:
            more = QLabel(f"还有 {len(selected) - 5} 类", self.summary)
            more.setFont(app_font(9))
            more.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
            self.summary_items.addWidget(more)

    def _toggle_all(self) -> None:
        # 若还有未选中的普通类别，则全选；否则全部回到默认（保护类与大文件除外）
        if self.scan_result is None:
            return
        all_selected = all(
            card.is_selected() or card.result.defn.protected
            for card in self.category_cards.values()
            if card.result.count > 0
        )
        for card in self.category_cards.values():
            if card.result.defn.protected:
                continue
            if card.result.count == 0:
                continue
            card.set_selected(not all_selected, emit=True)
        self.select_all_btn.setText("取消全选" if not all_selected else "全选")

    def _request_clean(self) -> None:
        selected = self._selected_categories()
        if selected:
            self.clean_requested.emit(selected)

    def on_clean_completed(self, result: CleanResult) -> None:
        # 清理完成后把这批类别标记为已清理，防止重复操作
        for key in result.by_category.keys():
            card = self.category_cards.get(key)
            if card is not None:
                card.set_selected(False, emit=False)
                card.check.setEnabled(False)
        self._recalc_summary()
        self.clean_btn.setEnabled(False)
        self.clean_btn.setText("清理已完成")
        self.summary_note.setText("清爽多了。报告已为你留好。")
        self.banner_text.setText(
            f"清理完成 · 释放 {format_size(result.freed_bytes)} · "
            f"{result.skipped_count} 个文件被跳过。")

    def set_error(self, text: str) -> None:
        self._scanning = False
        self.scan_status_pill.set_text("需要注意", self.tm.theme.orange)
        self.scan_current.setText(text)
        self.scan_ring.set_value(0, "!", "%", "暂停", text[:18])

    def show_empty(self) -> None:
        self._show_empty()
