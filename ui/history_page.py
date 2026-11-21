# -*- coding: utf-8 -*-
"""清理记录页：筛选面板 + 状态圆点列表 + 本地记录概览。"""
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from PySide6.QtCore import (QPoint, QRectF, Qt, Signal)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

from report import HistoryRecord, HistoryStore, human_duration, human_size, export_report
from cleaner import CleanResult, SkippedItem
from pathlib import Path
from scanner import CATEGORY_MAP
from ui.components import PageHeader, StatusPill, Tag
from ui.glass import EmptyState, GlassButton, GlassCard, Label, draw_glass
from ui.files_page import FilterChip, FilterGroup, FilterSection
from ui.icons import Glyph
from ui.theme import ThemeManager, app_font, category_color


class HistoryRow(QWidget):
    clicked = Signal(object)

    def __init__(self, record: HistoryRecord, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.record = record
        self._hover = 0.0
        self.setFixedHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(12)
        self.dot = QWidget(self)
        self.dot.setFixedSize(23, 23)
        self.dot.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.dot.paintEvent = lambda e: self._paint_dot()  # type: ignore[assignment]
        layout.addWidget(self.dot)
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(self._title(), self)
        title.setFont(app_font(12, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {self.tm.theme.text.name()}; background: transparent;")
        col.addWidget(title)
        sub = QLabel(self._subtitle(), self)
        sub.setFont(app_font(9, QFont.Weight.Normal, numeric=True))
        sub.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
        col.addWidget(sub)
        layout.addLayout(col, 1)
        right = QVBoxLayout()
        right.setSpacing(2)
        amount = QLabel(human_size(self.record.freed_bytes), self)
        amount.setFont(app_font(15, QFont.Weight.Bold, numeric=True))
        amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        amount.setStyleSheet(f"color: {self.tm.theme.text.name()}; background: transparent;")
        right.addWidget(amount)
        status = QLabel(self.record.status_text, self)
        status.setFont(app_font(9, QFont.Weight.Medium))
        status.setAlignment(Qt.AlignmentFlag.AlignRight)
        status.setStyleSheet(f"color: {self._status_color().name()}; background: transparent;")
        right.addWidget(status)
        layout.addLayout(right)
        chev = QWidget(self)
        chev.setFixedSize(24, 24)
        chev.setStyleSheet("background: transparent;")
        g = Glyph("chevron", QColor(self.tm.theme.faint), 12, 1.3, chev)
        g.move(6, 6)
        layout.addWidget(chev)

    def _status_color(self) -> QColor:
        c = category_color(self.tm.theme)
        if self.record.status == "success":
            return self.tm.theme.mint
        if self.record.status == "partial":
            return self.tm.theme.orange
        return QColor("#8E8C9B") if not self.tm.theme.is_dark else QColor("#9D98B6")

    def _title(self) -> str:
        n = len(self.record.categories)
        return f"C 盘清理 · {n} 类空间被整理" if n else "C 盘清理 · 轻量护理"

    def _subtitle(self) -> str:
        now = dt.datetime.now()
        ts = dt.datetime.fromtimestamp(self.record.timestamp)
        if ts.date() == now.date():
            prefix = "今天"
        elif ts.date() == (now - dt.timedelta(days=1)).date():
            prefix = "昨天"
        else:
            prefix = ts.strftime("%m月%d日")
        return (f"{prefix} {ts.strftime('%H:%M')}  ·  {self.record.deleted_count} 个文件  ·  "
                f"{self.record.skipped_count} 个跳过  ·  {human_duration(self.record.elapsed)}")

    def _paint_dot(self) -> None:
        p = QPainter(self.dot)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = self._status_color()
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 30))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(1, 1, 21, 21))
        p.setBrush(color)
        p.drawEllipse(QRectF(8, 8, 7, 7))

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = 1
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = 0
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.record)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover:
            p.setBrush(QColor(255, 255, 255, 13 if t.is_dark else 76))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(3, 2, -3, -2), 11, 11)
        p.setPen(QPen(t.divider, 1))
        p.drawLine(18, self.height() - 1, self.width() - 18, self.height() - 1)


class HistoryPage(QWidget):
    open_cleaner = Signal()
    record_selected = Signal(object)
    export_requested = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.store = HistoryStore()
        self.records = self.store.records
        self.filtered: List[HistoryRecord] = []
        self.filters: Dict[str, str] = {"cat": "all", "date": "all", "size": "all"}
        self.visible_rows: List[HistoryRow] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 8, 32, 22)
        root.setSpacing(16)
        self.header = PageHeader("清理记录",
                                 "每一次释放都有迹可循。记录只保存在本机，随时可以清空。",
                                 eyebrow="CLEANING JOURNAL")
        self.local = StatusPill("本机记录 · 不上传", self.tm.theme.mint)
        self.header.add_right(self.local)
        self.export_btn = GlassButton("导出最近报告", "secondary", "doc", self.header,
                                      height=36, min_width=128, compact=True)
        self.export_btn.clicked.connect(self._export_latest)
        self.header.add_right(self.export_btn)
        root.addWidget(self.header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)
        root.addLayout(body, 1)

        self.filter_panel = GlassCard(self, radius=16, padding=14, shadow=True)
        self.filter_panel.setFixedWidth(224)
        self.filter_panel.layout_.setSpacing(2)
        fh = QHBoxLayout()
        fh.addWidget(Label("筛选", 14, QFont.Weight.DemiBold, parent=self.filter_panel))
        fh.addStretch(1)
        reset = QLabel("重置", self.filter_panel)
        reset.setFont(app_font(9, QFont.Weight.DemiBold))
        reset.setStyleSheet(f"color: {self.tm.theme.accent.name()}; background: transparent;")
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.mousePressEvent = lambda e: self._reset()  # type: ignore[assignment]
        fh.addWidget(reset)
        self.filter_panel.layout_.addLayout(fh)
        self.filter_panel.layout_.addWidget(Label("把某一次记忆找出来。", 9,
                                                 color=self.tm.theme.faint,
                                                 parent=self.filter_panel))
        self.filter_panel.layout_.addSpacing(6)

        cat_content = QWidget(self.filter_panel)
        cl = QVBoxLayout(cat_content)
        cl.setContentsMargins(0, 0, 0, 8)
        self.cat_group = FilterGroup([("all", "全部"), ("temp", "临时"), ("browser", "浏览器"),
                                      ("logs", "日志"), ("update", "更新")], "all", 2, cat_content)
        self.cat_group.changed.connect(lambda k: self._on_filter("cat", k))
        cl.addWidget(self.cat_group)
        sec1 = FilterSection("类别", "全部", cat_content, True, self.filter_panel)
        self.filter_panel.layout_.addWidget(sec1)

        date_content = QWidget(self.filter_panel)
        dl = QVBoxLayout(date_content)
        dl.setContentsMargins(0, 0, 0, 8)
        self.date_group = FilterGroup([("all", "全部"), ("7", "近 7 天"),
                                       ("30", "近 30 天"), ("90", "近 90 天")], "all", 2, date_content)
        self.date_group.changed.connect(lambda k: self._on_filter("date", k))
        dl.addWidget(self.date_group)
        sec2 = FilterSection("日期", "全部", date_content, False, self.filter_panel)
        self.filter_panel.layout_.addWidget(sec2)

        size_content = QWidget(self.filter_panel)
        sl = QVBoxLayout(size_content)
        sl.setContentsMargins(0, 0, 0, 8)
        self.size_group = FilterGroup([("all", "全部"), ("s", "小于 1G"),
                                       ("m", "1–5G"), ("l", "5G 以上")], "all", 2, size_content)
        self.size_group.changed.connect(lambda k: self._on_filter("size", k))
        sl.addWidget(self.size_group)
        sec3 = FilterSection("释放大小", "全部", size_content, False, self.filter_panel)
        self.filter_panel.layout_.addWidget(sec3)
        self.filter_panel.layout_.addStretch(1)
        self.count_hint = Label("0 条记录", 9, color=self.tm.theme.faint, parent=self.filter_panel)
        self.filter_panel.layout_.addWidget(self.count_hint)
        body.addWidget(self.filter_panel)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(12)
        body.addLayout(right, 1)

        self.overview = GlassCard(self, radius=16, padding=18, glow=True)
        ov = QHBoxLayout()
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(24)
        self.overview.layout_.addLayout(ov)
        for attr, title, color, icon in [
            ("ov_total", "累计释放", self.tm.theme.accent, "sparkles"),
            ("ov_count", "护理次数", self.tm.theme.cyan, "clock"),
            ("ov_avg", "平均每次", self.tm.theme.mint, "shield"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            cap = QHBoxLayout()
            cap.addWidget(Glyph(icon, color, 13, 1.4, self.overview))
            cap.addWidget(Label(title, 10, QFont.Weight.Medium, color=self.tm.theme.muted,
                                parent=self.overview))
            cap.addStretch(1)
            col.addLayout(cap)
            value = Label("0", 24, QFont.Weight.Bold, parent=self.overview, display=True,
                          line_height=1.15)
            col.addWidget(value)
            setattr(self, attr, value)
            ov.addLayout(col, 1)
            if attr != "ov_avg":
                p = QWidget(self.overview)
                p.setFixedWidth(1)
                p.setStyleSheet(f"background: {self.tm.theme.divider.name()};")
                ov.addWidget(p)
        right.addWidget(self.overview)

        self.list_card = GlassCard(self, radius=18, padding=4, shadow=True)
        self.list_card.layout_.setSpacing(0)
        list_head = QHBoxLayout()
        list_head.setContentsMargins(18, 12, 18, 8)
        list_head.addWidget(Label("最近的活动", 13, QFont.Weight.DemiBold,
                                  parent=self.list_card))
        list_head.addStretch(1)
        self.filter_note = Label("全部记录", 9, color=self.tm.theme.faint, parent=self.list_card)
        list_head.addWidget(self.filter_note)
        self.list_card.layout_.addLayout(list_head)
        self.scroll = QScrollArea(self.list_card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows_host = QWidget()
        self.rows_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        self.scroll.setWidget(self.rows_host)
        self.list_card.layout_.addWidget(self.scroll, 1)
        self.empty = EmptyState("clock", "还没有清理记录",
                                "第一次清理后，这里会安静地留下每一次释放。", self.list_card)
        self.list_card.layout_.addWidget(self.empty)
        self.empty.hide()
        right.addWidget(self.list_card, 1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        try:
            self.store.load()
            self.records = self.store.records
        except Exception:
            self.records = []
        self._apply_filters()

    def _apply_filters(self) -> None:
        now = dt.datetime.now().timestamp()
        filtered: List[HistoryRecord] = []
        for rec in self.records:
            if self.filters["cat"] != "all" and self.filters["cat"] not in rec.categories:
                continue
            if self.filters["date"] != "all" and now - rec.timestamp > int(self.filters["date"]) * 86400:
                continue
            gb = rec.freed_bytes / 1024 ** 3
            if self.filters["size"] == "s" and not (gb < 1):
                continue
            if self.filters["size"] == "m" and not (1 <= gb < 5):
                continue
            if self.filters["size"] == "l" and gb < 5:
                continue
            filtered.append(rec)
        self.filtered = filtered
        self._update_overview()
        self._rebuild_rows()

    def _update_overview(self) -> None:
        total = sum(r.freed_bytes for r in self.records)
        count = len(self.records)
        avg = total // count if count else 0
        self.ov_total.setText(human_size(total))
        self.ov_count.setText(f"{count} 次")
        self.ov_avg.setText(human_size(avg))
        self.count_hint.setText(f"{len(self.filtered)} 条记录")
        self.filter_note.setText("全部记录" if len(self.filtered) == len(self.records)
                                 else f"筛选出 {len(self.filtered)} 条")
        self.export_btn.setEnabled(bool(self.records))

    def _rebuild_rows(self) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.visible_rows.clear()
        for rec in self.filtered:
            row = HistoryRow(rec, self.rows_host)
            row.clicked.connect(self.record_selected)
            self.rows_layout.addWidget(row)
            self.visible_rows.append(row)
        self.rows_layout.addStretch(1)
        self.empty.setVisible(not self.filtered)
        self.scroll.setVisible(bool(self.filtered))

    def _on_filter(self, kind: str, key: str) -> None:
        self.filters[kind] = key
        self._apply_filters()

    def _reset(self) -> None:
        self.filters = {"cat": "all", "date": "all", "size": "all"}
        for group in (self.cat_group, self.date_group, self.size_group):
            group.current = "all"
            for k, chip in group.chips.items():
                chip.setChecked(k == "all")
        self._apply_filters()

    def _export_latest(self) -> None:
        if self.records:
            self.export_requested.emit(self.records[0])

    def add_record(self, rec: HistoryRecord) -> None:
        self.refresh()
