# -*- coding: utf-8 -*-
"""仪表盘：C 盘空间环形仪表 + 三个迷你数据卡 + 今日护理建议。"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from report import HistoryStore, human_size
from scanner import CATEGORY_MAP, DiskStats, ScanResult, get_disk_stats
from ui.components import MiniStatCard, PageHeader, ReportBars, StatusPill, Tag
from ui.glass import GlassButton, GlassCard, Label, ProgressRing, format_size
from ui.icons import Glyph
from ui.theme import ThemeManager, app_font, category_color


class DashboardPage(QWidget):
    scan_requested = Signal()
    open_cleaner = Signal()
    open_files = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.scan_result: Optional[ScanResult] = None
        self.disk: DiskStats = get_disk_stats()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._build()
        self.tm.changed.connect(self._theme_changed)
        self.refresh_stats()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 8, 32, 22)
        root.setSpacing(18)
        self.header = PageHeader("早上好，你的 C 盘有点胖了",
                                 "今天也给它一点轻盈的空间。所有判断都在这台电脑上完成。",
                                 eyebrow="GOOD MORNING")
        self.health_pill = StatusPill("C 盘健康度：良好", self.tm.theme.mint)
        self.header.add_right(self.health_pill)
        root.addWidget(self.header)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(0, 0, 4, 4)
        self.body.setSpacing(16)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        self.body.addLayout(row)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(16)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(16)
        row.addLayout(left, 7)
        row.addLayout(right, 3)

        hero = GlassCard(self, radius=18, padding=20, glow=True)
        hero.layout_.setSpacing(10)
        hero_top = QHBoxLayout()
        hero_top.addWidget(Label("C 盘空间", 18, QFont.Weight.DemiBold, parent=hero))
        hero_top.addStretch(1)
        self.local_tag = Tag("实时 · 仅本机", self.tm.theme.cyan, hero, "shield")
        hero_top.addWidget(self.local_tag)
        hero.layout_.addLayout(hero_top)
        hero.layout_.addWidget(Label("每一次扫描，都只是你和这台电脑之间的对话。",
                                     11, QFont.Weight.Normal, color=self.tm.theme.muted, parent=hero))
        ring_host = QHBoxLayout()
        ring_host.addStretch(1)
        self.ring = ProgressRing(248, 16, "0", "GB", "可用空间", "", hero, big_size=42)
        ring_host.addWidget(self.ring)
        ring_host.addStretch(1)
        hero.layout_.addLayout(ring_host)
        stats = QHBoxLayout()
        stats.setContentsMargins(0, 2, 0, 0)
        stats.setSpacing(10)
        self.stat_used = MiniStatCard("已用空间", "0 GB", "正在读取 C 盘", self.tm.theme.cyan,
                                      "disk", hero)
        self.stat_free = MiniStatCard("可释放", "待扫描", "点一下，看看能轻多少", self.tm.theme.accent,
                                      "sparkles", hero)
        self.stat_last = MiniStatCard("上次清理", "还没有", "从今天开始记录", self.tm.theme.mint,
                                      "clock", hero)
        stats.addWidget(self.stat_used)
        stats.addWidget(self.stat_free)
        stats.addWidget(self.stat_last)
        hero.layout_.addLayout(stats)
        left.addWidget(hero)

        self.distribution = GlassCard(self, radius=16, padding=18)
        self.distribution.layout_.setSpacing(8)
        dist_top = QHBoxLayout()
        dist_top.addWidget(Label("空间都去哪儿了", 18, QFont.Weight.DemiBold,
                                 parent=self.distribution))
        dist_top.addStretch(1)
        self.dist_caption = QLabel("扫描后揭晓", self.distribution)
        self.dist_caption.setFont(app_font(10, QFont.Weight.Medium))
        self.dist_caption.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
        dist_top.addWidget(self.dist_caption)
        self.distribution.layout_.addLayout(dist_top)
        self.distribution.layout_.addWidget(Label(
            "每一类垃圾都有自己的颜色。先扫描，再决定要不要和它们告别。",
            11, QFont.Weight.Normal, color=self.tm.theme.muted, parent=self.distribution))
        self.bars = ReportBars([], self.distribution)
        self.bars.hide()
        self.distribution.layout_.addWidget(self.bars)
        self.empty_bars = QWidget(self.distribution)
        self.empty_bars.setFixedHeight(96)
        self.empty_bars.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        empty_row = QHBoxLayout(self.empty_bars)
        empty_row.setContentsMargins(0, 8, 0, 0)
        empty_row.setSpacing(7)
        colors = category_color(self.tm.theme)
        for key in ("temp", "update", "thumbnail", "prefetch", "browser", "logs"):
            dot = QWidget(self.empty_bars)
            dot.setFixedSize(8, 8)
            c = colors[key]
            dot.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},200);"
                              "border-radius: 4px;")
            empty_row.addWidget(dot)
            empty_row.addWidget(Label(CATEGORY_MAP[key].title, 9, QFont.Weight.Medium,
                                      color=self.tm.theme.faint, parent=self.empty_bars))
            empty_row.addSpacing(6)
        empty_row.addStretch(1)
        empty_row.addWidget(Label("立即扫描 →", 10, QFont.Weight.DemiBold,
                                  color=self.tm.theme.accent, parent=self.empty_bars))
        self.distribution.layout_.addWidget(self.empty_bars)
        left.addWidget(self.distribution)

        care = GlassCard(self, radius=18, padding=20, glow=True)
        care.layout_.setSpacing(12)
        care_head = QHBoxLayout()
        care_head.addWidget(Label("今日护理", 18, QFont.Weight.DemiBold, parent=care))
        care_head.addStretch(1)
        care_head.addWidget(Tag("建议", self.tm.theme.orange, care))
        care.layout_.addLayout(care_head)
        care.layout_.addWidget(Label("给 C 盘做一次不需要动脑的小扫除。",
                                     11, QFont.Weight.Normal, color=self.tm.theme.muted, parent=care))
        for icon, color, title, sub in [
            ("sparkles", self.tm.theme.cyan, "临时文件最容易长胖", "通常能腾出最多空间"),
            ("globe", self.tm.theme.mint, "浏览器缓存只清缓存", "登录状态和收藏都不会动"),
            ("shield", self.tm.theme.accent, "全部进入回收站", "后悔了也能随时还原"),
        ]:
            item = QWidget(care)
            item.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
            il = QHBoxLayout(item)
            il.setContentsMargins(0, 2, 0, 2)
            il.setSpacing(10)
            dot = QWidget(item)
            dot.setFixedSize(28, 28)
            c = QColor(color)
            dot.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},26);"
                              f"border: 1px solid rgba({c.red()},{c.green()},{c.blue()},65);"
                              "border-radius: 9px;")
            dot_glyph = Glyph(icon, color, 15, 1.45, dot)
            dot_glyph.move(6, 6)
            il.addWidget(dot)
            text_col = QVBoxLayout()
            text_col.setSpacing(0)
            text_col.addWidget(Label(title, 11, QFont.Weight.DemiBold, parent=item))
            text_col.addWidget(Label(sub, 10, QFont.Weight.Normal, color=self.tm.theme.muted, parent=item))
            il.addLayout(text_col, 1)
            care.layout_.addWidget(item)
        self.scan_btn = GlassButton("立即扫描", "primary", "sparkles", care, height=50)
        self.scan_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.scan_btn.clicked.connect(self.scan_requested)
        care.layout_.addSpacing(4)
        care.layout_.addWidget(self.scan_btn)
        right.addWidget(care)

        self.last_card = GlassCard(self, radius=16, padding=18)
        self.last_card.layout_.setSpacing(4)
        last_top = QHBoxLayout()
        last_top.addWidget(Label("上次清理", 13, QFont.Weight.DemiBold, parent=self.last_card))
        last_top.addStretch(1)
        self.last_time = Label("还没有记录", 10, QFont.Weight.Medium,
                               color=self.tm.theme.muted, parent=self.last_card)
        last_top.addWidget(self.last_time)
        self.last_card.layout_.addLayout(last_top)
        self.last_big = Label("0 GB", 34, QFont.Weight.Bold, parent=self.last_card, display=True,
                              line_height=1.1)
        self.last_big.setStyleSheet(self.last_big.styleSheet() + "letter-spacing: -1px;")
        self.last_card.layout_.addWidget(self.last_big)
        self.last_note = Label("每次释放都会安静地记在这里。", 10, QFont.Weight.Normal,
                               color=self.tm.theme.faint, parent=self.last_card)
        self.last_card.layout_.addWidget(self.last_note)
        right.addWidget(self.last_card)

        promise = GlassCard(self, radius=16, padding=16, shadow=False)
        promise.layout_.setSpacing(6)
        p_top = QHBoxLayout()
        p_top.addWidget(Glyph("lock", QColor(self.tm.theme.mint), 15, 1.4, promise))
        p_top.addWidget(Label("安全承诺", 12, QFont.Weight.DemiBold, parent=promise))
        p_top.addStretch(1)
        promise.layout_.addLayout(p_top)
        promise.layout_.addWidget(Label("不捆绑 · 不弹广告 · 不上传 · 不静默删除",
                                        10, QFont.Weight.Normal, color=self.tm.theme.muted,
                                        parent=promise))
        right.addWidget(promise)
        right.addStretch(1)

    # ------------------------------------------------------------------
    def _theme_changed(self, *_args) -> None:
        self.local_tag.color = self.tm.theme.cyan
        self.local_tag.update()

    def set_scan_result(self, result: ScanResult) -> None:
        self.scan_result = result
        self.disk = result.disk
        self.stat_used.set_value(human_size(self.disk.used), f"共 {human_size(self.disk.total)}")
        selected = sum(r.total_size for r in result.categories.values()
                       if r.defn.default_selected and not r.defn.protected)
        count = sum(r.count for r in result.categories.values()
                    if r.defn.default_selected and not r.defn.protected)
        self.stat_free.set_value(format_size(selected), f"{count} 个文件等待你确认")
        self.dist_caption.setText("最近一次扫描")
        self.bars.setVisible(True)
        self.empty_bars.setVisible(False)
        data = []
        colors = category_color(self.tm.theme)
        for key, cat in result.categories.items():
            if cat.defn.protected or cat.total_size <= 0:
                continue
            data.append((cat.defn.title, cat.defn.icon, cat.total_size, colors[key]))
        data.sort(key=lambda item: item[2], reverse=True)
        self.bars.set_data(data[:6])
        self._update_ring()
        self._update_header()

    def refresh_stats(self) -> None:
        if self.scan_result is not None:
            self.disk = self.scan_result.disk
        else:
            self.disk = get_disk_stats()
        self._update_ring()
        self._update_header()
        self.stat_used.set_value(human_size(self.disk.used), f"共 {human_size(self.disk.total)}")
        try:
            store = HistoryStore()
            if store.records:
                rec = store.records[0]
                stamp = dt.datetime.fromtimestamp(rec.timestamp).strftime("%m月%d日 %H:%M")
                self.stat_last.set_value(human_size(rec.freed_bytes), "从回收站可随时还原")
                self.last_time.setText(stamp)
                self.last_big.setText(human_size(rec.freed_bytes))
                self.last_note.setText(f"{rec.deleted_count} 个文件 · {rec.status_text}")
            else:
                self.stat_last.set_value("还没有", "从今天开始记录")
                self.last_time.setText("还没有记录")
                self.last_big.setText("0 GB")
                self.last_note.setText("每次释放都会安静地记在这里。")
        except Exception:
            pass

    def _update_ring(self) -> None:
        disk = self.disk
        if not disk.total:
            return
        free_gb = disk.free / 1024 ** 3
        total_gb = disk.total / 1024 ** 3
        value_text = f"{free_gb:.0f}" if free_gb >= 10 else f"{free_gb:.1f}"
        self.ring.set_value(disk.used_ratio, value_text, "GB", "可用空间",
                            f"共 {total_gb:.0f} GB · 已用 {disk.used_ratio * 100:.0f}%",
                            animate=True)

    def _update_header(self) -> None:
        hour = dt.datetime.now().hour
        if hour < 6:
            greeting = "夜深了"
        elif hour < 11:
            greeting = "早上好"
        elif hour < 14:
            greeting = "中午好"
        elif hour < 18:
            greeting = "下午好"
        else:
            greeting = "晚上好"
        ratio = self.disk.used_ratio
        if ratio >= 0.9:
            phrase = "你的 C 盘需要一点紧急护理"
            color = self.tm.theme.coral
        elif ratio >= 0.78:
            phrase = "你的 C 盘有点胖了"
            color = self.tm.theme.orange
        elif ratio >= 0.62:
            phrase = "你的 C 盘状态还不错"
            color = self.tm.theme.mint
        else:
            phrase = "你的 C 盘很轻盈"
            color = self.tm.theme.mint
        self.header.title.setText(f"{greeting}，{phrase}")
        self.health_pill.set_text(f"C 盘健康度：{self.disk.health_text}", color)
        if self.scan_result is None:
            self.header.subtitle.setText(
                f"已用 {human_size(self.disk.used)} / {human_size(self.disk.total)}，"
                "所有判断都在这台电脑上完成。")
        else:
            self.header.subtitle.setText(
                f"最近一次扫描找到 {self.scan_result.total_count} 个文件，等待你决定；"
                f"全部处理最多释放 {human_size(self.scan_result.total_size)}。")
