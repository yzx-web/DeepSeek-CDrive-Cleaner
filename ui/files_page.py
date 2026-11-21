# -*- coding: utf-8 -*-
"""大文件体检页：左侧折叠筛选面板 + 右侧文件清单。"""
from __future__ import annotations

import datetime as dt
import os
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import (Property, QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt,
                            Signal)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from scanner import BIG_FILE_MIN, CategoryResult, FileEntry, ScanResult
from system_utils import show_in_explorer
from ui.components import (PageHeader, RoundCheck, StatusPill, Tag)
from ui.glass import EmptyState, GlassButton, GlassCard, Label, SkeletonBlock, format_size
from ui.icons import Glyph, draw_glyph
from ui.theme import ThemeManager, app_font


TYPE_DEFS = {
    "video": ("视频", "video", QColor("#FF8A8A")),
    "archive": ("压缩包", "folder", QColor("#FFB867")),
    "disk": ("磁盘映像", "disk", QColor("#C99BFF")),
    "other": ("其他", "doc", QColor("#64D2FF")),
}
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".m4v", ".ts"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}
DISK_EXT = {".iso", ".img", ".vmdk", ".vhdx", ".vdi", ".dmg", ".bin"}


def classify(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in ARCHIVE_EXT:
        return "archive"
    if ext in DISK_EXT:
        return "disk"
    return "other"


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text
        self.setToolTip(text)
        self._update_elide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_elide()

    def _update_elide(self) -> None:
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(20, self.width())))


class FilterChip(QAbstractButton):  # type: ignore[no-redef]
    def __init__(self, key: str, text: str, selected: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.key = key
        self._text = text
        self.setCheckable(True)
        self.setChecked(selected)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(app_font(10, QFont.Weight.Medium))
        self._hover = 0.0
        self._anim = QPropertyAnimation(self, b"hoverAmount", self)
        self._anim.setDuration(130)
        fm = QFontMetrics(self.font())
        self.setFixedSize(fm.horizontalAdvance(text) + 18, 28)
        self.tm.changed.connect(self.update)

    def setText(self, text: str) -> None:  # noqa: N802
        self._text = text
        fm = QFontMetrics(self.font())
        self.setFixedSize(fm.horizontalAdvance(text) + 18, 28)
        self.update()

    def get_hover(self) -> float:
        return self._hover

    def set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hoverAmount = Property(float, get_hover, set_hover)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._anim.stop(); self._anim.setEndValue(1); self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._anim.stop(); self._anim.setEndValue(0); self._anim.start()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        selected = self.isChecked()
        if selected:
            p.setBrush(QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 55 if t.is_dark else 38))
            p.setPen(QPen(QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 135), 1))
        else:
            p.setBrush(QColor(255, 255, 255, 22 + int(12 * self._hover) if t.is_dark else 95 + int(15 * self._hover)))
            p.setPen(QPen(QColor(255, 255, 255, 45 if t.is_dark else 150), 1))
        p.drawRoundedRect(r, 8, 8)
        p.setFont(self.font())
        p.setPen(t.accent if selected else t.subtext)
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), self._text)


class FilterGroup(QWidget):
    changed = Signal(str)

    def __init__(self, options: List[Tuple[str, str]], current: str = "all",
                 columns: int = 2, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.options = options
        self.current = current
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(6)
        self.chips: Dict[str, FilterChip] = {}
        for i, (key, text) in enumerate(options):
            chip = FilterChip(key, text, key == current, self)
            chip.clicked.connect(lambda _c=False, k=key: self._select(k))
            self.chips[key] = chip
            grid.addWidget(chip, i // columns, i % columns)
        for c in range(columns):
            grid.setColumnStretch(c, 1)

    def _select(self, key: str) -> None:
        if key == self.current:
            return
        self.current = key
        for k, chip in self.chips.items():
            chip.setChecked(k == key)
        self.changed.emit(key)


class InlineFilterBar(GlassCard):
    """横向筛选条：把筛选从高高的左栏变成一条轻量工具条。"""

    def __init__(self, groups: List[Tuple[str, "FilterGroup"]], reset_cb,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, radius=14, padding=10, shadow=True)
        self.tm = ThemeManager.instance()
        self.setFixedHeight(70)
        self.layout_.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        for index, (title, group) in enumerate(groups):
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(3)
            cap = Label(title, 9, QFont.Weight.DemiBold, color=self.tm.theme.faint, parent=self)
            col.addWidget(cap)
            col.addWidget(group)
            if index:
                divider = QWidget(self)
                divider.setFixedWidth(1)
                divider.setStyleSheet(f"background: {self.tm.theme.divider.name()};")
                divider.setFixedHeight(38)
                row.addWidget(divider, 0, Qt.AlignmentFlag.AlignVCenter)
            row.addLayout(col)
        row.addStretch(1)
        reset = QLabel("重置", self)
        reset.setFont(app_font(9, QFont.Weight.DemiBold))
        reset.setStyleSheet(f"color: {self.tm.theme.accent.name()}; background: transparent;")
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.mousePressEvent = lambda e: reset_cb()  # type: ignore[assignment]
        row.addWidget(reset, 0, Qt.AlignmentFlag.AlignBottom)
        self.layout_.addLayout(row)


class FilterSection(QWidget):
    def __init__(self, title: str, subtitle: str, content: QWidget, expanded: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self._expanded = expanded
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = QPushButton(self)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setFixedHeight(38)
        self.header.setStyleSheet("background: transparent; border: none;")
        self.header.clicked.connect(self.toggle)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(2, 0, 2, 0)
        hl.setSpacing(7)
        self.title = QLabel(title, self.header)
        self.title.setFont(app_font(11, QFont.Weight.DemiBold))
        self.title.setStyleSheet(f"color: {self.tm.theme.text.name()}; background: transparent;")
        hl.addWidget(self.title)
        hl.addStretch(1)
        self.count = QLabel(subtitle, self.header)
        self.count.setFont(app_font(9))
        self.count.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
        hl.addWidget(self.count)
        root.addWidget(self.header)
        self.content = content
        self.content.setParent(self)
        self.content.setVisible(expanded)
        root.addWidget(self.content)
        self._anim = QPropertyAnimation(self.content, b"maximumHeight", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._chev = QLabel("⌄", self.header)
        self._chev.setFont(app_font(12, QFont.Weight.Bold))
        self._chev.setStyleSheet(f"color: {self.tm.theme.muted.name()}; background: transparent;")
        hl.addWidget(self._chev)
        self._update_chev()
        self.content.setMaximumHeight(16777215 if expanded else 0)

    def _update_chev(self) -> None:
        self._chev.setText("⌃" if self._expanded else "⌄")

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._update_chev()
        target = self.content.sizeHint().height() if self._expanded else 0
        self.content.setVisible(True)
        self._anim.stop()
        self._anim.setStartValue(self.content.maximumHeight() if self.content.isVisible() else 0)
        self._anim.setEndValue(target)
        self._anim.start()

    def set_summary(self, text: str) -> None:
        self.count.setText(text)


class TypeIcon(QWidget):
    def __init__(self, kind: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.kind = kind
        self.setFixedSize(38, 38)

    def paintEvent(self, event) -> None:  # noqa: N802
        name, icon, color = TYPE_DEFS[self.kind]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 38))
        p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 72), 1))
        p.drawRoundedRect(r, 10, 10)
        draw_glyph(p, icon, QRectF(9, 9, 20, 20), color, 1.5)


class BigFileRow(GlassCard):
    toggled = Signal(object, bool)
    reveal = Signal(object)

    def __init__(self, entry: FileEntry, selected: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, radius=14, padding=12, hover=True, shadow=False)
        self.tm = ThemeManager.instance()
        self.entry = entry
        self.kind = classify(str(entry.path))
        self._selected = selected
        self.setFixedHeight(76)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(11)
        self.check = RoundCheck(selected, self.tm.theme.accent, self, 20)
        self.check.toggled.connect(self._toggle)
        row.addWidget(self.check, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(TypeIcon(self.kind, self))
        text = QVBoxLayout()
        text.setSpacing(2)
        name = ElidedLabel(entry.path.name, self)
        name.setFont(app_font(12, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {self.tm.theme.text.name()}; background: transparent;")
        text.addWidget(name)
        path = ElidedLabel(str(entry.path.parent), self)
        path.setFont(app_font(9))
        path.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
        text.addWidget(path)
        row.addLayout(text, 1)
        meta = QVBoxLayout()
        meta.setSpacing(2)
        size = QLabel(format_size(entry.size), self)
        size.setFont(app_font(13, QFont.Weight.DemiBold, numeric=True))
        size.setAlignment(Qt.AlignmentFlag.AlignRight)
        size.setStyleSheet(f"color: {self.tm.theme.text.name()}; background: transparent;")
        meta.addWidget(size)
        date = QLabel(dt.datetime.fromtimestamp(entry.modified).strftime("%Y/%m/%d"), self)
        date.setFont(app_font(9, QFont.Weight.Normal, numeric=True))
        date.setAlignment(Qt.AlignmentFlag.AlignRight)
        date.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
        meta.addWidget(date)
        row.addLayout(meta)
        opener = QWidget(self)
        opener.setFixedSize(28, 28)
        opener.setStyleSheet("background: transparent;")
        glyph = Glyph("external", QColor(self.tm.theme.muted), 15, 1.4, opener)
        glyph.move(6.5, 6.5)
        opener.setCursor(Qt.CursorShape.PointingHandCursor)
        opener.setToolTip("在资源管理器中显示")
        opener.mousePressEvent = lambda e: self.reveal.emit(self.entry)  # type: ignore[assignment]
        row.addWidget(opener)
        self.layout_.addLayout(row)

    def _toggle(self, checked: bool) -> None:
        self._selected = checked
        self.toggled.emit(self.entry, checked)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.check.blockSignals(True)
        self.check.setChecked(selected)
        self.check.blockSignals(False)

    def is_selected(self) -> bool:
        return self._selected

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.set_selected(not self._selected)
            self.toggled.emit(self.entry, self._selected)
        super().mouseReleaseEvent(event)


class BigFilesPage(QWidget):
    scan_requested = Signal()
    clean_requested = Signal(list)
    reveal_requested = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.entries: List[FileEntry] = []
        self.rows: List[BigFileRow] = []
        self.selected: Dict[str, FileEntry] = {}
        self.filters: Dict[str, str] = {"type": "all", "date": "all", "size": "all"}
        self.scan_result: Optional[ScanResult] = None
        self._scanning = False
        self._build()
        self.tm.changed.connect(self._theme_changed)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 8, 32, 22)
        root.setSpacing(16)
        self.header = PageHeader("大文件体检",
                                 "超过 500MB 的文件都在这里。它们不一定是垃圾，所以默认不勾选。",
                                 eyebrow="BIG FILE CHECKUP")
        self.health = StatusPill("只列清单 · 不擅自处理", self.tm.theme.orange)
        self.header.add_right(self.health)
        root.addWidget(self.header)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        root.addLayout(body, 1)

        self.type_group = FilterGroup([("all", "全部"), ("video", "视频"), ("archive", "压缩包"),
                                       ("disk", "磁盘映像"), ("other", "其他")], "all", 5, self)
        self.type_group.changed.connect(lambda k: self._on_filter("type", k))
        self.date_group = FilterGroup([("all", "全部"), ("7", "近 7 天"), ("30", "近 30 天"),
                                       ("90", "近 90 天")], "all", 4, self)
        self.date_group.changed.connect(lambda k: self._on_filter("date", k))
        self.size_group = FilterGroup([("all", "全部"), ("s", "0.5–1G"), ("m", "1–5G"),
                                       ("l", "5G 以上")], "all", 4, self)
        self.size_group.changed.connect(lambda k: self._on_filter("size", k))
        self.filter_bar = InlineFilterBar([
            ("类别", self.type_group), ("日期", self.date_group), ("大小区间", self.size_group),
        ], self._reset_filters, self)
        body.addWidget(self.filter_bar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        body.addLayout(right, 1)

        self.topbar = GlassCard(self, radius=14, padding=12, shadow=False)
        self.topbar.setFixedHeight(62)
        tl = QHBoxLayout()
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        self.result_label = Label("还没有体检过", 12, QFont.Weight.Medium, parent=self.topbar)
        tl.addWidget(self.result_label, 1)
        self.select_all_label = QLabel("全选当前", self.topbar)
        self.select_all_label.setFont(app_font(10, QFont.Weight.DemiBold))
        self.select_all_label.setStyleSheet(f"color: {self.tm.theme.accent.name()}; background: transparent;")
        self.select_all_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all_label.mousePressEvent = lambda e: self._select_all_visible()  # type: ignore[assignment]
        tl.addWidget(self.select_all_label)
        self.scan_btn = GlassButton("重新体检", "secondary", "search", self.topbar,
                                    height=36, min_width=104, compact=True)
        self.scan_btn.clicked.connect(self.scan_requested)
        tl.addWidget(self.scan_btn)
        self.topbar.layout_.addLayout(tl)
        right.addWidget(self.topbar)

        self.stack_host = QWidget(self)
        self.stack_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        stack = QVBoxLayout(self.stack_host)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(10)
        right.addWidget(self.stack_host, 1)

        # 空状态
        self.empty = GlassCard(self.stack_host, radius=18, padding=24, glow=True)
        self.empty.layout_.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.empty.layout_.addStretch(1)
        self.empty.layout_.addWidget(EmptyState("search", "先做一次大文件体检",
                                               "我们会在你的 C 盘用户目录中找出超过 500MB 的文件。\n只列清单，不会动任何一个字节。",
                                               self.empty))
        self.empty_btn = GlassButton("开始体检", "primary", "search", self.empty, height=48,
                                     min_width=190)
        self.empty_btn.clicked.connect(self.scan_requested)
        er = QHBoxLayout()
        er.addStretch(1)
        er.addWidget(self.empty_btn)
        er.addStretch(1)
        self.empty.layout_.addLayout(er)
        self.empty.layout_.addStretch(1)
        stack.addWidget(self.empty)

        # 骨架加载
        self.loading = GlassCard(self.stack_host, radius=18, padding=22)
        self.loading.layout_.setSpacing(12)
        self.loading.layout_.addWidget(Label("正在浏览大文件…", 18, QFont.Weight.Bold,
                                             parent=self.loading, display=True))
        self.loading_hint = Label("只统计体积，不读取文件内容。", 10, color=self.tm.theme.muted,
                                  parent=self.loading)
        self.loading.layout_.addWidget(self.loading_hint)
        for i in range(5):
            sk = QWidget(self.loading)
            sl = QHBoxLayout(sk)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.setSpacing(10)
            sl.addWidget(SkeletonBlock(38, 38, 10, sk))
            col = QVBoxLayout()
            col.setSpacing(5)
            col.addWidget(SkeletonBlock(240 - i * 16, 12, 6, sk))
            col.addWidget(SkeletonBlock(320 - i * 20, 9, 5, sk))
            sl.addLayout(col, 1)
            sl.addWidget(SkeletonBlock(70, 14, 6, sk))
            self.loading.layout_.addWidget(sk)
        stack.addWidget(self.loading)

        # 列表
        self.list_host = QWidget(self.stack_host)
        self.list_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.scroll = QScrollArea(self.list_host)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows_host = QWidget()
        self.rows_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 4, 0)
        self.rows_layout.setSpacing(8)
        self.scroll.setWidget(self.rows_host)
        self.list_layout.addWidget(self.scroll, 1)
        self.no_match = Label("这个筛选条件下没有大文件。", 11, color=self.tm.theme.faint,
                              parent=self.list_host)
        self.no_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_match.hide()
        self.list_layout.addWidget(self.no_match)
        stack.addWidget(self.list_host)

        # 底部清理条
        self.action_bar = GlassCard(self, radius=14, padding=12, shadow=True)
        self.action_bar.setFixedHeight(68)
        ab = QHBoxLayout()
        ab.setContentsMargins(0, 0, 0, 0)
        ab.setSpacing(12)
        self.selection_label = Label("已选 0 项 · 0 B", 11, QFont.Weight.DemiBold,
                                     parent=self.action_bar, numeric=True)
        ab.addWidget(self.selection_label, 1)
        self.clean_btn = GlassButton("清理选中（进回收站）", "danger", "trash", self.action_bar,
                                     height=42, min_width=180)
        self.clean_btn.setEnabled(False)
        self.clean_btn.clicked.connect(self._request_clean)
        ab.addWidget(self.clean_btn)
        self.action_bar.layout_.addLayout(ab)
        right.addWidget(self.action_bar)
        self.action_bar.hide()

        self._show_empty()

    # ------------------------------------------------------------------
    def _scan_begin(self) -> None:
        self._scanning = True
        self.health.set_text("正在浏览大文件", self.tm.theme.cyan)
        self.empty.hide()
        self.loading.show()
        self.list_host.hide()
        self.action_bar.hide()
        self.topbar.show()
        self.result_label.setText("正在浏览 C 盘用户目录…")
        self.loading_hint.setText("只统计体积，不读取文件内容。")

    def begin_scan(self) -> None:
        self._scan_begin()

    def on_scan_progress(self, count: int, size: int) -> None:
        self.loading_hint.setText(f"已经看过 {count:,} 个文件 · 找到 {format_size(size)} 大文件")

    def on_scan_finished(self, result: ScanResult) -> None:
        self._scanning = False
        self.set_scan_result(result)

    def set_scan_result(self, result: ScanResult) -> None:
        self.scan_result = result
        cat = result.categories.get("bigfiles")
        self.entries = list(cat.files) if cat else []
        self.selected.clear()
        self._search_seen = cat.scanned_count if cat else 0
        self._apply_filters()
        self.health.set_text("只列清单 · 不擅自处理", self.tm.theme.orange)
        if not self.entries:
            self._show_empty()
            self.empty_btn.setText("重新体检")
        else:
            self.stack_host_finish()
            self.rescan_text = "重新体检"

    def stack_host_finish(self) -> None:
        self.empty.hide()
        self.loading.hide()
        self.list_host.show()

    def _show_empty(self) -> None:
        self.empty.show()
        self.loading.hide()
        self.list_host.hide()
        self.action_bar.hide()
        self._rebuild_topbar_empty()

    def _rebuild_topbar_empty(self) -> None:
        self.result_label.setText("还没有体检过")
        self.select_all_label.setVisible(False)
        self.scan_btn.setText("开始体检")

    def _rebuild_rows(self) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows.clear()
        for entry in self._filtered():
            row = BigFileRow(entry, str(entry.path) in self.selected, self.rows_host)
            row.toggled.connect(self._row_toggled)
            row.reveal.connect(self._reveal)
            self.rows_layout.addWidget(row)
            self.rows.append(row)
        self.rows_layout.addStretch(1)
        self.no_match.setVisible(bool(self.entries) and not self.rows)
        self.scroll.setVisible(bool(self.rows))
        self.health.set_text("只列清单 · 不擅自处理", self.tm.theme.orange)
        self._update_selection()

    def _filtered(self) -> List[FileEntry]:
        out = []
        now = dt.datetime.now().timestamp()
        for entry in self.entries:
            if self.filters["type"] != "all" and classify(str(entry.path)) != self.filters["type"]:
                continue
            if self.filters["date"] != "all":
                days = int(self.filters["date"])
                if now - entry.modified > days * 86400:
                    continue
            if self.filters["size"] != "all":
                gb = entry.size / 1024 ** 3
                if self.filters["size"] == "s" and not (0.5 <= gb < 1):
                    continue
                if self.filters["size"] == "m" and not (1 <= gb < 5):
                    continue
                if self.filters["size"] == "l" and gb < 5:
                    continue
            out.append(entry)
        return out

    def _apply_filters(self) -> None:
        filtered = self._filtered()
        total = sum(e.size for e in filtered)
        if self.entries:
            self.stack_host_finish()
            self.result_label.setText(f"找到 {len(filtered)} 个 · 共 {format_size(total)}")
            self.select_all_label.setVisible(True)
        self._rebuild_rows()

    def _on_filter(self, kind: str, key: str) -> None:
        self.filters[kind] = key
        self._apply_filters()

    def _reset_filters(self) -> None:
        for key in ("type", "date", "size"):
            self.filters[key] = "all"
        for group in (self.type_group, self.date_group, self.size_group):
            group.current = "all"
            for k, chip in group.chips.items():
                chip.setChecked(k == "all")
        self._apply_filters()

    def _row_toggled(self, entry: FileEntry, selected: bool) -> None:
        key = str(entry.path)
        if selected:
            self.selected[key] = entry
        else:
            self.selected.pop(key, None)
        self._update_selection()

    def _select_all_visible(self) -> None:
        visible = self._filtered()
        all_selected = all(str(e.path) in self.selected for e in visible)
        for entry in visible:
            key = str(entry.path)
            if all_selected:
                self.selected.pop(key, None)
            else:
                self.selected[key] = entry
        for row in self.rows:
            row.set_selected(str(row.entry.path) in self.selected)
        self.select_all_label.setText("取消全选" if not all_selected else "全选当前")
        self._update_selection()

    def _update_selection(self) -> None:
        size = sum(e.size for e in self.selected.values())
        self.selection_label.setText(f"已选 {len(self.selected)} 项 · {format_size(size)}")
        self.clean_btn.setEnabled(bool(self.selected))
        if self.selected:
            self.action_bar.show()
        else:
            self.action_bar.hide()
        self.select_all_label.setText("全选当前")

    def _request_clean(self) -> None:
        if self.selected:
            self.clean_requested.emit(list(self.selected.values()))

    def _reveal(self, entry: FileEntry) -> None:
        show_in_explorer(entry.path)
        self.reveal_requested.emit(entry)

    def on_clean_completed(self) -> None:
        for key in list(self.selected.keys()):
            self.selected.pop(key, None)
        self._update_selection()
        self._apply_filters()

    def set_error(self, text: str) -> None:
        self.health.set_text("需要管理员权限", self.tm.theme.orange)
        self.result_label.setText(text)
        self.loading.hide()
        self.list_host.hide()
        self.empty.show()

    def _theme_changed(self, *_args) -> None:
        for row in self.rows:
            row.update()
