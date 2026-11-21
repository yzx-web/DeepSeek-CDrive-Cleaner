# -*- coding: utf-8 -*-
"""设置页：外观、行为、权限、隐私与关于。"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

from app_settings import APP_NAME, APP_VERSION, SettingsStore, data_dir
from system_utils import (is_admin, pystray_available, relaunch_as_admin,
                         set_startup, set_weekly_reminder)
from ui.components import PageHeader, SegmentedControl, StatusPill, Tag
from ui.glass import GlassButton, GlassCard, IconButton, Label, Separator, Switch, draw_glass
from ui.icons import Glyph, LogoMark
from ui.theme import ThemeManager, app_font


class SettingRow(QWidget):
    toggled = Signal(str, bool)

    def __init__(self, key: str, title: str, subtitle: str, checked: bool,
                 parent: Optional[QWidget] = None, last: bool = False) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.key = key
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMinimumHeight(52)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(2)
        title_label = Label(title, 12, QFont.Weight.DemiBold, parent=self)
        col.addWidget(title_label)
        sub = Label(subtitle, 9, QFont.Weight.Normal, color=self.tm.theme.muted,
                    parent=self, line_height=1.3)
        col.addWidget(sub)
        row.addLayout(col, 1)
        self.switch = Switch(checked, self)
        self.switch.toggled.connect(lambda v, k=key: self.toggled.emit(k, v))
        row.addWidget(self.switch)
        if not last:
            self.divider = QWidget(self)
            self.divider.setFixedHeight(1)
            self.divider.setStyleSheet(f"background: {self.tm.theme.divider.name()};")
        self.tm.changed.connect(self._theme)
        if not last:
            self.divider.setGeometry(0, self.height() - 1, self.width(), 1)

    def _theme(self, *_args) -> None:
        if hasattr(self, "divider"):
            self.divider.setStyleSheet(f"background: {self.tm.theme.divider.name()};")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "divider"):
            self.divider.setGeometry(0, self.height() - 1, self.width(), 1)


class DangerCard(GlassCard):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, radius=16, padding=14, shadow=True)
        self.tm = ThemeManager.instance()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = QColor(self.tm.theme.coral)
        c.setAlpha(115)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(c, 1.2))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), self.radius, self.radius)


class SettingsPage(QWidget):
    toast_requested = Signal(str)
    theme_changed = Signal(str)
    admin_relaunch_requested = Signal()
    clear_history_requested = Signal()
    reset_requested = Signal()

    def __init__(self, store: SettingsStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.store = store
        self._syncing = False
        self._build()
        self.tm.changed.connect(self._theme_changed)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 8, 32, 22)
        root.setSpacing(14)
        self.header = PageHeader("设置",
                                 "把清理工具调成你顺手的样子。所有偏好都只保存在本机。",
                                 eyebrow="PREFERENCES")
        self.admin_pill = StatusPill("普通权限", self.tm.theme.orange)
        self.header.add_right(self.admin_pill)
        root.addWidget(self.header)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        body = QHBoxLayout(host)
        body.setContentsMargins(0, 0, 4, 0)
        body.setSpacing(16)
        self.scroll.setWidget(host)
        root.addWidget(self.scroll, 1)
        left = QVBoxLayout()
        left.setSpacing(16)
        right = QVBoxLayout()
        right.setSpacing(16)
        body.addLayout(left, 1)
        body.addLayout(right, 1)

        # 外观
        appearance = GlassCard(self, radius=16, padding=16, glow=True)
        appearance.layout_.setSpacing(8)
        appearance.layout_.addWidget(Label("外观", 18, QFont.Weight.Bold, parent=appearance,
                                           display=True))
        appearance.layout_.addWidget(Label("跟随系统，或选一个你今天喜欢的光。", 10,
                                           color=self.tm.theme.muted, parent=appearance))
        self.theme_segment = SegmentedControl([
            ("auto", "自动"), ("light", "浅色"), ("dark", "深色")
        ], self.store.data.theme, appearance)
        self.theme_segment.changed.connect(self._change_theme)
        appearance.layout_.addWidget(self.theme_segment)
        left.addWidget(appearance)

        # 行为
        behavior = GlassCard(self, radius=16, padding=16)
        behavior.layout_.setSpacing(1)
        behavior.layout_.addWidget(Label("行为", 18, QFont.Weight.Bold, parent=behavior,
                                         display=True))
        behavior.layout_.addWidget(Label("这些开关会改变软件“怎么陪着你”。", 10,
                                         color=self.tm.theme.muted, parent=behavior))
        behavior.layout_.addSpacing(3)
        self._rows: Dict[str, SettingRow] = {}
        definitions = [
            ("startup", "开机时安静启动", "登录 Windows 后在托盘里待命，不打扰你。"),
            ("auto_shutdown", "清理完成后自动关机", "适合睡前护理；会先弹出 60 秒倒计时，可取消。"),
            ("weekly_reminder", "每周日提醒扫描", "通过 Windows 计划任务，在周日 10:00 轻提醒一次。"),
            ("close_to_tray", "关闭窗口时留在托盘", "点关闭只收起界面，右键托盘可真正退出。"),
            ("reduce_motion", "减少动效", "低电量或低配电脑上更顺滑，保留玻璃质感。"),
        ]
        for i, (key, title, sub) in enumerate(definitions):
            checked = getattr(self.store.data, key)
            row = SettingRow(key, title, sub, checked, behavior, last=i == len(definitions) - 1)
            row.toggled.connect(self._change_switch)
            behavior.layout_.addWidget(row)
            self._rows[key] = row
        left.addWidget(behavior)

        # 关于
        about = GlassCard(self, radius=16, padding=16, glow=True)
        about.layout_.setSpacing(7)
        top = QHBoxLayout()
        top.addWidget(LogoMark(34, about))
        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        name_col.addWidget(Label("DeepSeek", 16, QFont.Weight.Bold, parent=about))
        name_col.addWidget(Label("C盘清理专家 · v4.1.0", 10, QFont.Weight.Medium,
                                color=self.tm.theme.muted, parent=about))
        top.addLayout(name_col, 1)
        top.addWidget(Tag("本地模式", self.tm.theme.mint, about))
        about.layout_.addLayout(top)
        about.layout_.addWidget(Label(
            "一个安静、透明、有点好看的 C 盘清理工具。\n"
            "不捆绑安装，不弹广告，不上传任何路径或文件。",
            10, color=self.tm.theme.muted, parent=about, line_height=1.55))
        facts = QHBoxLayout()
        facts.setSpacing(16)
        for title, value in [("界面", "PySide6 · Qt 6"), ("删除", "系统回收站"), ("版本", APP_VERSION)]:
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(Label(title, 9, color=self.tm.theme.faint, parent=about))
            col.addWidget(Label(value, 10, QFont.Weight.DemiBold, parent=about))
            facts.addLayout(col)
        facts.addStretch(1)
        about.layout_.addLayout(facts)
        left.addWidget(about)
        left.addStretch(1)

        # 权限
        security = GlassCard(self, radius=16, padding=14)
        security.layout_.setSpacing(8)
        sec_head = QHBoxLayout()
        sec_head.addWidget(Label("安全与权限", 18, QFont.Weight.Bold, parent=security,
                                 display=True))
        sec_head.addStretch(1)
        self.admin_badge = Tag("普通权限", self.tm.theme.orange, security, "shield")
        sec_head.addWidget(self.admin_badge)
        security.layout_.addLayout(sec_head)
        security.layout_.addWidget(Label(
            "普通模式足以完成大部分清理；当需要触碰 Windows 系统目录时，程序会问你。",
            10, color=self.tm.theme.muted, parent=security))
        self.admin_text = Label("当前以普通权限运行，系统目录中的部分文件会被跳过。", 9,
                                color=self.tm.theme.faint, parent=security, line_height=1.4)
        security.layout_.addWidget(self.admin_text)
        self.admin_btn = GlassButton("以管理员身份重新启动", "secondary", "shield", security,
                                     height=38)
        self.admin_btn.clicked.connect(self.admin_relaunch_requested)
        security.layout_.addWidget(self.admin_btn)
        note = QLabel("UAC 会弹出 Windows 官方确认框；本软件不会绕过它。", security)
        note.setFont(app_font(9))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")
        security.layout_.addWidget(note)
        right.addWidget(security)

        # 隐私
        privacy = GlassCard(self, radius=16, padding=14, glow=True)
        privacy.layout_.setSpacing(7)
        privacy.layout_.addWidget(Label("隐私与数据", 18, QFont.Weight.Bold,
                                        parent=privacy, display=True))
        for icon, color, title, sub in [
            ("disk", self.tm.theme.cyan, "记录只在本机", "不联网校验，不做云端同步。"),
            ("lock", self.tm.theme.mint, "密码与 Cookie 免疫", "浏览器缓存清理只碰 Cache 类目录。"),
            ("trash", self.tm.theme.orange, "回收站是最后防线", "本软件拒绝代为永久清空回收站。"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(9)
            row.addWidget(Glyph(icon, QColor(color), 16, 1.4, privacy))
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(Label(title, 10, QFont.Weight.DemiBold, parent=privacy))
            col.addWidget(Label(sub, 9, color=self.tm.theme.muted, parent=privacy))
            row.addLayout(col, 1)
            privacy.layout_.addLayout(row)
        privacy.layout_.addSpacing(4)
        path_label = Label(str(data_dir()), 8, color=self.tm.theme.faint, parent=privacy)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        privacy.layout_.addWidget(path_label)
        row2 = QHBoxLayout()
        self.open_data_btn = GlassButton("打开数据目录", "ghost", "external", privacy, height=34,
                                         min_width=118, compact=True)
        self.open_data_btn.clicked.connect(lambda: __import__("system_utils").open_path(data_dir()))
        row2.addWidget(self.open_data_btn)
        row2.addStretch(1)
        privacy.layout_.addLayout(row2)
        right.addWidget(privacy)

        # 危险区
        danger = DangerCard(self)
        danger.layout_.setSpacing(6)
        danger.layout_.addWidget(Label("危险区", 16, QFont.Weight.Bold, parent=danger,
                                       display=True))
        danger.layout_.addWidget(Label("清理的是工具的记忆，不会删除你的文件。",
                                       9, color=self.tm.theme.muted, parent=danger))
        clear = GlassButton("清空清理记录", "danger", "trash", danger, height=36)
        clear.clicked.connect(self.clear_history_requested)
        danger.layout_.addWidget(clear)
        reset = GlassButton("恢复默认设置", "ghost", None, danger, height=34, compact=True)
        reset.clicked.connect(self.reset_requested)
        danger.layout_.addWidget(reset)
        right.addWidget(danger)
        right.addStretch(1)

        self.refresh_permissions()

    # ------------------------------------------------------------------
    def _change_theme(self, mode: str) -> None:
        self.store.set("theme", mode)
        self.tm.set_mode(mode)
        self.theme_changed.emit(mode)

    def _change_switch(self, key: str, value: bool) -> None:
        if self._syncing:
            return
        if key == "startup":
            ok = set_startup(value)
            if not ok:
                self._revert(key, not value)
                self.toast_requested.emit("系统没有允许写入开机启动项，已为你恢复。")
                return
        if key == "weekly_reminder":
            ok = set_weekly_reminder(value)
            if not ok:
                self._revert(key, not value)
                self.toast_requested.emit("计划任务创建失败，可能需要管理员权限。")
                return
        self.store.set(key, value)
        tips = {
            "auto_shutdown": "开启后，清理完成会先出现 60 秒关机倒计时。",
            "close_to_tray": "关闭窗口会留在托盘；右键托盘可以真正退出。",
            "reduce_motion": "已减少动效，玻璃质感仍然保留。",
            "startup": "开机自启已更新。" if value else "开机自启已关闭。",
            "weekly_reminder": "每周日 10:00 会轻提醒一次。" if value else "每周提醒已取消。",
        }
        if key in tips:
            self.toast_requested.emit(tips[key])

    def _revert(self, key: str, value: bool) -> None:
        row = self._rows.get(key)
        if row:
            self._syncing = True
            row.switch.setChecked(value)
            self._syncing = False

    def sync_from_store(self) -> None:
        self._syncing = True
        self.theme_segment.set_current(self.store.data.theme)
        for key, row in self._rows.items():
            row.switch.setChecked(bool(getattr(self.store.data, key)))
        self._syncing = False
        self.refresh_permissions()

    def refresh_permissions(self) -> None:
        admin = is_admin()
        if admin:
            self.admin_pill.set_text("管理员权限", self.tm.theme.mint)
            self.admin_badge.text_value = "管理员权限"
            self.admin_badge.color = self.tm.theme.mint
            self.admin_text.setText("当前以管理员权限运行，系统目录也能完整清理。")
            self.admin_btn.setText("已是管理员权限")
            self.admin_btn.setEnabled(False)
        else:
            self.admin_pill.set_text("普通权限", self.tm.theme.orange)
            self.admin_badge.text_value = "普通权限"
            self.admin_badge.color = self.tm.theme.orange
            self.admin_text.setText("当前以普通权限运行，系统目录中的部分文件会被跳过。")
            self.admin_btn.setText("以管理员身份重新启动")
            self.admin_btn.setEnabled(True)
            self.admin_btn.setVisible(True)
        self.admin_badge.updateGeometry()
        self.admin_badge.update()

    def _theme_changed(self, *_args) -> None:
        self.admin_badge.update()
