# -*- coding: utf-8 -*-
"""主窗口、页面路由、系统托盘、清理确认与完成报告弹窗。"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QObject, QPoint, QPointF, QRect,
                            QRectF, QSize, Qt, QTimer, QPropertyAnimation, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QIcon,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QMenu, QScrollArea, QSizeGrip,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from app_settings import APP_NAME, APP_VERSION, Settings, SettingsStore
from cleaner import CleanResult, CleanWorker
from report import (HistoryRecord, HistoryStore, export_record, export_report)
from scanner import CATEGORY_MAP, CATEGORIES, CategoryResult, FileEntry, ScanResult, ScanWorker, get_disk_stats
from system_utils import (TrayController, cancel_shutdown, is_admin, open_path,
                         pystray_available, relaunch_as_admin, schedule_shutdown,
                         show_in_explorer)
from ui.clean_page import CleanPage
from ui.components import ReportBars, StatusPill
from ui.dashboard import DashboardPage
from ui.files_page import BigFilesPage
from ui.glass import (GlassButton, GlassCard, GlassModal, IconButton, Label, ProgressRing,
                      Toast, draw_glass, draw_shadow, format_size)
from ui.history_page import HistoryPage
from ui.icons import Glyph, draw_glyph
from ui.settings_page import SettingsPage
from ui.sidebar import Sidebar
from ui.theme import ThemeManager, app_font, category_color


class TrafficButton(QAbstractButton):
    def __init__(self, kind: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = ThemeManager.instance()
        self.kind = kind
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip({"close": "关闭", "min": "最小化", "max": "最大化"}[kind])
        self._hover = 0.0
        self._anim = QPropertyAnimation(self, b"hoverAmount", self)
        self._anim.setDuration(140)
        self.tm.changed.connect(self.update)

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
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colors = {"close": "#FF5F57", "min": "#FEBC2E", "max": "#28C840"}
        base = QColor(colors[self.kind])
        hover = QColor(base)
        hover = hover.lighter(118)
        p.setBrush(base if self._hover < 0.5 else hover)
        p.setPen(QPen(QColor(255, 255, 255, 80), 0.8))
        r = QRectF(self.width() / 2 - 6.5, self.height() / 2 - 6.5, 13, 13)
        p.drawEllipse(r)
        # 小高光
        gloss = QColor(255, 255, 255, 55)
        p.setBrush(gloss)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(r.left() + 2, r.top() + 1.5, 7, 5))
        if self._hover > 0.35:
            color = QColor(30, 26, 38, 105)
            draw_glyph(p, self.kind, QRectF(r.center().x() - 6, r.center().y() - 6, 12, 12), color, 1.2)


class TitleBar(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window_ref = window
        self.tm = ThemeManager.instance()
        self.setFixedHeight(40)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 4, 0)
        layout.setSpacing(4)
        dot = QWidget(self)
        dot.setFixedSize(7, 7)
        dot.setStyleSheet("background: #30D158; border-radius: 3px;")
        layout.addWidget(dot)
        local = QLabel("本机安全模式", self)
        local.setFont(app_font(9, QFont.Weight.Medium))
        local.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;"
                            "letter-spacing: 0.4px;")
        layout.addWidget(local)
        layout.addStretch(1)
        self.btns: Dict[str, TrafficButton] = {}
        for kind in ("min", "max", "close"):
            b = TrafficButton(kind, self)
            b.clicked.connect(lambda _c=False, k=kind: self.window_ref.window_action(k))
            layout.addWidget(b)
            self.btns[kind] = b
        self.tm.changed.connect(self._theme)

    def _theme(self, *_args) -> None:
        for child in self.findChildren(QLabel):
            child.setStyleSheet(f"color: {self.tm.theme.faint.name()}; background: transparent;")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.window_ref.window_action("max")


class ResizeHandle(QWidget):
    def __init__(self, window: "MainWindow", edges: Qt.Edge) -> None:
        super().__init__(window)
        self.window_ref = window
        self.edges = edges
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setCursor(self._cursor_for(edges))

    @staticmethod
    def _cursor_for(edges: Qt.Edge) -> Qt.CursorShape:
        both = Qt.Edge.LeftEdge | Qt.Edge.RightEdge | Qt.Edge.TopEdge | Qt.Edge.BottomEdge
        if edges & both == Qt.Edge.LeftEdge | Qt.Edge.TopEdge:
            return Qt.CursorShape.SizeFDiagCursor
        if edges & both == Qt.Edge.RightEdge | Qt.Edge.BottomEdge:
            return Qt.CursorShape.SizeFDiagCursor
        if edges & both == Qt.Edge.RightEdge | Qt.Edge.TopEdge:
            return Qt.CursorShape.SizeBDiagCursor
        if edges & both == Qt.Edge.LeftEdge | Qt.Edge.BottomEdge:
            return Qt.CursorShape.SizeBDiagCursor
        if edges & Qt.Edge.LeftEdge or edges & Qt.Edge.RightEdge:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemResize(self.edges)


class PageSwitcher(QStackedWidget):
    """250ms 滑动 + 交叉淡入，像 iOS 页面间的轻轻一推。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._overlay: Optional[QLabel] = None
        self._anim: Optional[QPropertyAnimation] = None

    def switch_to(self, widget: QWidget, forward: bool = True) -> None:
        if widget is self.currentWidget():
            return
        old = self.currentWidget()
        if old is None:
            self.setCurrentWidget(widget)
            return
        try:
            snap = old.grab()
        except Exception:
            snap = QPixmap()
        self.setCurrentWidget(widget)
        new_page = widget
        overlay = QLabel(self)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.setPixmap(snap)
        overlay.setGeometry(self.rect())
        overlay.show()
        overlay.raise_()
        eff = QGraphicsOpacityEffect(overlay)
        eff.setOpacity(0.94)
        overlay.setGraphicsEffect(eff)
        new_eff = QGraphicsOpacityEffect(new_page)
        new_eff.setOpacity(0.36)
        new_page.setGraphicsEffect(new_eff)
        group = QPropertyAnimation(overlay, b"pos", self)
        group.setDuration(250)
        group.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.setStartValue(QPoint(0, 0))
        group.setEndValue(QPoint(-38 if forward else 38, 0))
        alpha = QPropertyAnimation(eff, b"opacity", self)
        alpha.setDuration(220)
        alpha.setStartValue(0.94)
        alpha.setEndValue(0.0)
        fade = QPropertyAnimation(new_eff, b"opacity", self)
        fade.setDuration(250)
        fade.setStartValue(0.36)
        fade.setEndValue(1.0)
        fade.finished.connect(lambda: self._finish_switch(overlay, new_page))
        group.start()
        alpha.start()
        fade.start()
        self._overlay = overlay
        self._anim = group
        self._fade = fade
        self._alpha = alpha

    def _finish_switch(self, overlay: QLabel, new_page: QWidget) -> None:
        try:
            overlay.hide()
            overlay.deleteLater()
            new_page.setGraphicsEffect(None)
        except Exception:
            pass
        self._overlay = None


class TrayBridge(QObject):
    open_requested = Signal()
    scan_requested = Signal()
    quit_requested = Signal()


class MainWindow(QWidget):
    def __init__(self, demo: bool = False, remind: bool = False, startup_min: bool = False) -> None:
        super().__init__()
        self.tm = ThemeManager.instance()
        self.store = SettingsStore()
        self.settings = self.store.data
        self.demo = demo
        self.history = HistoryStore()
        self.scan_worker: Optional[ScanWorker] = None
        self.clean_worker: Optional[CleanWorker] = None
        self._modal: Optional[GlassModal] = None
        self._force_quit = False
        self._tray_notified = False
        self._last_result: Optional[CleanResult] = None
        self._active_page = "dashboard"
        self._build_window()
        self._build_pages()
        self._build_tray()
        if demo:
            QTimer.singleShot(120, self._apply_demo)
        if remind:
            QTimer.singleShot(900, lambda: self._toast.show_message(
                "周日的轻提醒：C 盘该做一次护理了，扫描只要十几秒。", 5200))
        if startup_min:
            QTimer.singleShot(200, self.hide)

    # ------------------------------------------------------------------ window
    def _build_window(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(self._resource("assets/app_icon.png"))))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1440, 900)
        self.setMinimumSize(1180, 760)
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(14, 14, 14, 14)
        self.root_layout.setSpacing(0)
        self.shell = AuroraShell(self.tm)
        self.shell.setObjectName("Shell")
        self.root_layout.addWidget(self.shell)
        self.shell_layout = QHBoxLayout(self.shell)
        self.shell_layout.setContentsMargins(16, 10, 16, 16)
        self.shell_layout.setSpacing(16)

        self.sidebar = Sidebar(self.shell)
        self.sidebar.nav_changed.connect(self.navigate)
        self.sidebar.quit_requested.connect(self._confirm_quit)
        self.shell_layout.addWidget(self.sidebar)

        content = QWidget(self.shell)
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.titlebar = TitleBar(self)
        content_layout.addWidget(self.titlebar)
        self.pages = PageSwitcher(content)
        content_layout.addWidget(self.pages, 1)
        self.shell_layout.addWidget(content, 1)

        self.toast = Toast(self.shell)
        self._build_resize_handles()
        self.tm.changed.connect(self._theme_changed)

    def _build_resize_handles(self) -> None:
        self._handles: List[ResizeHandle] = []
        for edges in (
            Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge,
            Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.TopEdge,
            Qt.Edge.LeftEdge | Qt.Edge.BottomEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge,
        ):
            h = ResizeHandle(self, edges)
            h.setStyleSheet("background: transparent;")
            h.hide()
            self._handles.append(h)

    def _build_pages(self) -> None:
        self.dashboard = DashboardPage(self.pages)
        self.clean_page = CleanPage(self.pages)
        self.files_page = BigFilesPage(self.pages)
        self.history_page = HistoryPage(self.pages)
        self.settings_page = SettingsPage(self.store, self.pages)
        self.page_map: Dict[str, QWidget] = {
            "dashboard": self.dashboard,
            "cleaner": self.clean_page,
            "files": self.files_page,
            "history": self.history_page,
            "settings": self.settings_page,
        }
        for page in self.page_map.values():
            self.pages.addWidget(page)

        self.dashboard.scan_requested.connect(lambda: self.start_scan("cleaner"))
        self.dashboard.open_cleaner.connect(lambda: self.navigate("cleaner"))
        self.clean_page.scan_requested.connect(lambda: self.start_scan("cleaner"))
        self.clean_page.cancel_scan_requested.connect(self.cancel_scan)
        self.clean_page.clean_requested.connect(self._confirm_clean)
        self.clean_page.recycle_open_requested.connect(self._open_recycle)
        self.files_page.scan_requested.connect(lambda: self.start_scan("files"))
        self.files_page.clean_requested.connect(self._confirm_bigfiles)
        self.history_page.record_selected.connect(self._show_history_report)
        self.history_page.export_requested.connect(self._export_record)
        self.settings_page.toast_requested.connect(self.show_toast)
        self.settings_page.admin_relaunch_requested.connect(self._relaunch_admin)
        self.settings_page.clear_history_requested.connect(self._confirm_clear_history)
        self.settings_page.reset_requested.connect(self._confirm_reset)

        self.pages.setCurrentWidget(self.dashboard)

    def _resource(self, rel: str) -> Path:
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base) / rel
        return Path(__file__).resolve().parents[1] / rel

    # ------------------------------------------------------------------ navigation
    def navigate(self, key: str) -> None:
        if key not in self.page_map:
            return
        forward = True
        order = ["dashboard", "cleaner", "files", "history", "settings"]
        try:
            forward = order.index(key) >= order.index(self._active_page)
        except ValueError:
            pass
        self._active_page = key
        self.sidebar.select(key, emit=False)
        self.pages.switch_to(self.page_map[key], forward)
        if key == "dashboard":
            self.dashboard.refresh_stats()
        elif key == "history":
            self.history_page.refresh()
        elif key == "settings":
            self.settings_page.refresh_permissions()

    # ------------------------------------------------------------------ scan
    def start_scan(self, origin: str = "cleaner") -> None:
        if self.scan_worker is not None and self.scan_worker.isRunning():
            self.navigate("cleaner")
            self.show_toast("已经在扫描了，稍等它一会儿。")
            return
        if origin == "cleaner":
            self.navigate("cleaner")
        self.clean_page.begin_scan()
        self.files_page.begin_scan()
        worker = ScanWorker(parent=self)
        self.scan_worker = worker
        worker.signals.category_progress.connect(self._on_scan_progress)
        worker.signals.category_done.connect(self.clean_page.on_scan_category_done)
        worker.signals.overall.connect(self.clean_page.on_scan_overall)
        worker.signals.finished.connect(self._on_scan_finished)
        worker.signals.failed.connect(self._on_scan_failed)
        worker.signals.cancelled.connect(self._on_scan_cancelled)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_scan_progress(self, key: str, count: int, size: int) -> None:
        self.clean_page.on_scan_category_progress(key, count, size)
        if key == "bigfiles":
            self.files_page.on_scan_progress(count, size)

    def _on_scan_finished(self, result: ScanResult) -> None:
        self.scan_worker = None
        self.clean_page.on_scan_finished(result)
        self.files_page.on_scan_finished(result)
        self.dashboard.set_scan_result(result)
        if result.errors:
            self.show_toast("有些系统角落需要管理员权限，已自动跳过；其余清理不受影响。", 4200)
        self.settings_page.refresh_permissions()

    def _on_scan_failed(self, message: str) -> None:
        self.scan_worker = None
        self.clean_page.set_error(message)
        self.files_page.set_error(message)
        self.show_toast("扫描没有完成，请稍后再试。", 3800)

    def _on_scan_cancelled(self) -> None:
        self.scan_worker = None
        self.clean_page.show_empty()
        self.navigate("cleaner")
        self.show_toast("扫描已取消，没有动任何文件。")

    def cancel_scan(self) -> None:
        if self.scan_worker is not None:
            self.scan_worker.cancel()
            self.clean_page.scan_current.setText("正在停下，请稍等…")
            self.show_toast("收到，正在安全地取消扫描。")

    # ------------------------------------------------------------------ clean
    def _confirm_clean(self, categories: List[CategoryResult]) -> None:
        if not categories:
            return
        total_size = sum(c.total_size for c in categories)
        total_count = sum(c.count for c in categories)
        modal = self._new_modal(540, danger=True)
        modal.set_danger(True)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(12)
        icon = QWidget(modal)
        icon.setFixedSize(44, 44)
        icon.setStyleSheet("background: rgba(255,69,58,28); border: 1px solid rgba(255,69,58,80);"
                           "border-radius: 12px;")
        glyph = Glyph("warning", QColor(self.tm.theme.coral), 21, 1.5, icon)
        glyph.move(11.5, 11.5)
        head.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(Label("要和这些文件告别吗？", 21, QFont.Weight.Bold, parent=modal,
                            display=True))
        col.addWidget(Label("所有文件都会进入回收站，想反悔随时可以还原。",
                            11, color=self.tm.theme.muted, parent=modal))
        head.addLayout(col, 1)
        modal.add_layout(head)
        summary = GlassCard(modal, radius=14, padding=16, shadow=False)
        sl = QHBoxLayout()
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        sl.addWidget(Label("预计释放", 11, color=self.tm.theme.muted, parent=summary))
        sl.addStretch(1)
        amount = Label(format_size(total_size), 28, QFont.Weight.Bold, parent=summary,
                       display=True, line_height=1.2)
        sl.addWidget(amount)
        summary.layout_.addLayout(sl)
        detail = QHBoxLayout()
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(6)
        colors = category_color(self.tm.theme)
        for cat in sorted(categories, key=lambda c: c.total_size, reverse=True)[:5]:
            c = colors[cat.key]
            dot = QWidget(summary)
            dot.setFixedSize(7, 7)
            dot.setStyleSheet(f"background:{c.name()}; border-radius:3px;")
            detail.addWidget(dot)
            detail.addWidget(Label(cat.defn.title, 9, color=self.tm.theme.subtext,
                                   parent=summary))
            detail.addSpacing(3)
        detail.addStretch(1)
        summary.layout_.addLayout(detail)
        modal.add(summary)
        note = Label(
            f"共 {total_count:,} 个文件。回收站类别会被保留，本软件不会代为永久清空。"
            + ("\n当前是普通权限，个别系统文件可能因权限不足被跳过。"
               if not is_admin() else ""),
            10, color=self.tm.theme.muted, parent=modal, line_height=1.55)
        modal.add(note)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        cancel = GlassButton("再想想", "secondary", None, modal, height=46)
        cancel.clicked.connect(modal.close_modal)
        btn_row.addWidget(cancel, 1)
        confirm = GlassButton("确认清理", "danger", "trash", modal, height=46)
        btn_row.addWidget(confirm, 1)
        modal.add_layout(btn_row)
        self._clean_armed = False
        self._clean_timer = QTimer(modal)
        self._clean_timer.setSingleShot(True)

        def arm() -> None:
            if self._clean_armed:
                modal.close_modal()
                self._execute_clean(categories)
                return
            self._clean_armed = True
            confirm.setText("请再点一次确认")
            confirm.update()
            note.setText("真的确认了？这一步会把所选文件移入回收站，并保存一条清理记录。")
            self._clean_timer.timeout.connect(lambda: reset_arm())
            self._clean_timer.start(4200)

        def reset_arm() -> None:
            self._clean_armed = False
            confirm.setText("确认清理")
            confirm.update()

        confirm.clicked.connect(arm)
        self._show_modal(modal)

    def _confirm_bigfiles(self, entries: List[FileEntry]) -> None:
        cat = CategoryResult(key="bigfiles", files=entries,
                             total_size=sum(e.size for e in entries))
        self._confirm_clean([cat])

    def _execute_clean(self, categories: List[CategoryResult]) -> None:
        if self.clean_worker is not None:
            return
        self._clean_selected_keys = [c.key for c in categories]
        worker = CleanWorker(categories, allow_big_files=True, parent=self)
        self.clean_worker = worker
        worker.signals.progress.connect(self._on_clean_progress)
        worker.signals.finished.connect(self._on_clean_finished)
        worker.finished.connect(worker.deleteLater)
        modal = self._new_modal(486, danger=False)
        modal.dismissable = False
        modal.add(Label("正在把文件送进回收站", 22, QFont.Weight.Bold, parent=modal,
                        display=True))
        modal.add(Label("不是消失，只是换一个地方待着。你随时可以还原。",
                        11, color=self.tm.theme.muted, parent=modal))
        ring_row = QHBoxLayout()
        ring_row.addStretch(1)
        self.clean_ring = ProgressRing(170, 12, "0", "%", "已处理", "准备中", modal,
                                       big_size=34)
        ring_row.addWidget(self.clean_ring)
        ring_row.addStretch(1)
        modal.add_layout(ring_row)
        self.clean_count_label = Label("正在准备…", 11, color=self.tm.theme.subtext,
                                       parent=modal, numeric=True)
        self.clean_count_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        modal.add(self.clean_count_label)
        self.clean_current_label = Label("文件会逐个进入回收站", 9,
                                         color=self.tm.theme.faint, parent=modal)
        self.clean_current_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        modal.add(self.clean_current_label)
        self.clean_cancel_btn = GlassButton("安全停止", "secondary", "close", modal, height=40)
        self.clean_cancel_btn.clicked.connect(self._cancel_clean)
        modal.add(self.clean_cancel_btn)
        self._clean_modal = modal
        self._show_modal(modal)
        QTimer.singleShot(150, worker.start)

    def _on_clean_progress(self, done: int, total: int, freed: int, name: str) -> None:
        progress = done / max(1, total)
        self.clean_ring.set_value(progress, f"{progress * 100:.0f}", "%", "已处理",
                                  f"{done}/{total}")
        self.clean_count_label.setText(f"已处理 {done:,} / {total:,} 个 · 已释放 {format_size(freed)}")
        self.clean_current_label.setText(f"正在处理：{name}")

    def _cancel_clean(self) -> None:
        if self.clean_worker is not None:
            self.clean_worker.cancel()
            self.clean_cancel_btn.setText("正在安全停止…")
            self.clean_cancel_btn.setEnabled(False)

    def _on_clean_finished(self, result: CleanResult) -> None:
        self.clean_worker = None
        self._last_result = result
        self.history.append(result, self._clean_selected_keys)
        self.settings.last_clean_at = time.time()
        self.settings.last_clean_bytes = result.freed_bytes
        self.store.save()
        try:
            if self._modal is not None:
                self._modal.close_modal()
        except Exception:
            pass
        self.clean_page.on_clean_completed(result)
        self.files_page.on_clean_completed()
        self.dashboard.refresh_stats()
        self.history_page.refresh()
        QTimer.singleShot(240, lambda: self._show_completion(result))

    # ------------------------------------------------------------------ modals
    def _new_modal(self, width: int = 500, danger: bool = False) -> GlassModal:
        if self._modal is not None:
            try:
                self._modal.close_modal()
            except Exception:
                pass
        modal = GlassModal(self.shell, width=width, padding=26)
        modal.set_danger(danger)
        self._modal = modal
        return modal

    def _show_modal(self, modal: GlassModal) -> None:
        modal.show_modal()

    def _show_completion(self, result: CleanResult) -> None:
        modal = self._new_modal(620)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        head.addWidget(Label("清理完成，C 盘轻了一点", 22, QFont.Weight.Bold, parent=modal,
                             display=True))
        head.addStretch(1)
        head.addWidget(StatusPill("已留好记录", self.tm.theme.mint))
        modal.add_layout(head)
        hero = GlassCard(modal, radius=16, padding=18, glow=True)
        hero.layout_.setSpacing(2)
        hero.layout_.addWidget(Label("本次释放", 11, QFont.Weight.Medium,
                                     color=self.tm.theme.muted, parent=hero))
        big = Label(format_size(result.freed_bytes), 46, QFont.Weight.Bold, parent=hero,
                    display=True, line_height=1.15)
        big.setStyleSheet(big.styleSheet() + "letter-spacing:-1.6px;")
        hero.layout_.addWidget(big)
        hero.layout_.addWidget(Label(
            f"{result.deleted_count} 个文件已进入回收站 · 随时可以还原",
            10, color=self.tm.theme.muted, parent=hero))
        modal.add(hero)
        colors = category_color(self.tm.theme)
        data = []
        for key, (deleted, freed) in sorted(result.by_category.items(),
                                            key=lambda kv: kv[1][1], reverse=True):
            if freed <= 0:
                continue
            defn = CATEGORY_MAP.get(key)
            if defn:
                data.append((defn.title, defn.icon, freed, colors[key]))
        if data:
            bars = ReportBars(data[:5], modal)
            modal.add(bars)
        if result.skipped_count:
            note = Label(
                f"有 {result.skipped_count} 个文件正在被使用或权限不足，它们躲过了这次清理。"
                "这不会影响其它文件。", 10, color=self.tm.theme.orange, parent=modal,
                line_height=1.5)
            modal.add(note)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        export_btn = GlassButton("导出 TXT 到桌面", "secondary", "doc", modal, height=46)
        export_btn.clicked.connect(lambda: self._export_result(result, export_btn))
        btn_row.addWidget(export_btn, 1)
        done_btn = GlassButton("完成", "primary", "check", modal, height=46)
        done_btn.clicked.connect(modal.close_modal)
        btn_row.addWidget(done_btn, 1)
        modal.add_layout(btn_row)
        modal.closed.connect(self._after_completion_closed)
        self._show_modal(modal)

    def _after_completion_closed(self) -> None:
        if self.settings.auto_shutdown:
            self._show_shutdown_countdown()

    def _export_result(self, result: CleanResult, button: Optional[GlassButton] = None) -> None:
        try:
            path = export_report(result, self._clean_selected_keys)
            self.show_toast(f"报告已放到桌面：{path.name}", 4200)
            if button is not None:
                button.setText("已导出到桌面")
                button.setEnabled(False)
        except Exception as exc:
            self.show_toast(f"导出失败：{exc}", 3600)

    def _export_record(self, record: HistoryRecord) -> None:
        try:
            path = export_record(record)
            self.show_toast(f"报告已导出：{path.name}", 3600)
        except Exception as exc:
            self.show_toast(f"导出失败：{exc}", 3600)

    def _show_history_report(self, record: HistoryRecord) -> None:
        modal = self._new_modal(620)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(Label("那一次的清理", 22, QFont.Weight.Bold, parent=modal, display=True))
        head.addStretch(1)
        head.addWidget(StatusPill(record.status_text,
                                  {"success": self.tm.theme.mint,
                                   "partial": self.tm.theme.orange,
                                   "cancelled": QColor("#8E8C9B")}[record.status]))
        modal.add_layout(head)
        stamp = time.strftime("%Y年%m月%d日 %H:%M", time.localtime(record.timestamp))
        modal.add(Label(f"{stamp} · {result_duration(record.elapsed)} · 全部进入回收站",
                        10, color=self.tm.theme.muted, parent=modal))
        hero = GlassCard(modal, radius=16, padding=18, glow=True)
        hero.layout_.setSpacing(2)
        hero.layout_.addWidget(Label("释放空间", 11, color=self.tm.theme.muted, parent=hero))
        big = Label(format_size(record.freed_bytes), 44, QFont.Weight.Bold, parent=hero,
                    display=True, line_height=1.15)
        hero.layout_.addWidget(big)
        hero.layout_.addWidget(Label(f"{record.deleted_count} 个文件 · {record.skipped_count} 个被跳过",
                                     10, color=self.tm.theme.muted, parent=hero))
        modal.add(hero)
        colors = category_color(self.tm.theme)
        data = []
        for key, info in sorted(record.categories.items(), key=lambda kv: kv[1].get("freed", 0), reverse=True):
            defn = CATEGORY_MAP.get(key)
            if defn and info.get("freed", 0) > 0:
                data.append((defn.title, defn.icon, int(info.get("freed", 0)), colors[key]))
        if data:
            modal.add(ReportBars(data[:6], modal))
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        export_btn = GlassButton("导出这份报告", "secondary", "doc", modal, height=44)
        export_btn.clicked.connect(lambda: (self._export_record(record), export_btn.setText("已导出")))
        btn_row.addWidget(export_btn, 1)
        close_btn = GlassButton("关闭", "primary", None, modal, height=44)
        close_btn.clicked.connect(modal.close_modal)
        btn_row.addWidget(close_btn, 1)
        modal.add_layout(btn_row)
        self._show_modal(modal)

    def _show_shutdown_countdown(self) -> None:
        schedule_shutdown(60)
        modal = self._new_modal(440, danger=True)
        modal.set_danger(True)
        modal.add(Label("C 盘清爽了，准备休息", 22, QFont.Weight.Bold, parent=modal,
                        display=True))
        modal.add(Label("60 秒后会自动关机。你还有时间改变主意。", 11,
                         color=self.tm.theme.muted, parent=modal))
        self.shutdown_ring = ProgressRing(150, 11, "60", "秒", "后关机", "清理后自动关机",
                                          modal, big_size=36)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.shutdown_ring)
        row.addStretch(1)
        modal.add_layout(row)
        cancel = GlassButton("取消关机", "secondary", "power", modal, height=44)
        cancel.clicked.connect(lambda: self._cancel_shutdown(modal))
        modal.add(cancel)
        self._shutdown_left = 60
        self._shutdown_timer = QTimer(modal)
        self._shutdown_timer.timeout.connect(lambda: self._tick_shutdown())
        self._shutdown_timer.start(1000)
        self._show_modal(modal)

    def _tick_shutdown(self) -> None:
        self._shutdown_left = max(0, self._shutdown_left - 1)
        if hasattr(self, "shutdown_ring"):
            self.shutdown_ring.set_value(self._shutdown_left / 60, str(self._shutdown_left),
                                         "秒", "后关机", "清理后自动关机", animate=False)

    def _cancel_shutdown(self, modal: GlassModal) -> None:
        cancel_shutdown()
        if hasattr(self, "_shutdown_timer"):
            self._shutdown_timer.stop()
        modal.close_modal()
        self.show_toast("已取消关机，安心休息。")

    def _confirm_clear_history(self) -> None:
        modal = self._new_modal(460, danger=True)
        modal.set_danger(True)
        modal.add(Label("清空所有清理记录？", 21, QFont.Weight.Bold, parent=modal, display=True))
        modal.add(Label("只删除这台电脑上的历史记录，不会动你的任何文件。",
                        11, color=self.tm.theme.muted, parent=modal))
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        cancel = GlassButton("取消", "secondary", None, modal, height=44)
        cancel.clicked.connect(modal.close_modal)
        buttons.addWidget(cancel, 1)
        do = GlassButton("清空记录", "danger", "trash", modal, height=44)
        do.clicked.connect(lambda: self._clear_history(modal))
        buttons.addWidget(do, 1)
        modal.add_layout(buttons)
        self._show_modal(modal)

    def _clear_history(self, modal: GlassModal) -> None:
        self.history.clear()
        self.history_page.refresh()
        modal.close_modal()
        self.show_toast("清理记录已清空。")

    def _confirm_reset(self) -> None:
        modal = self._new_modal(460, danger=True)
        modal.set_danger(True)
        modal.add(Label("恢复默认设置？", 21, QFont.Weight.Bold, parent=modal, display=True))
        modal.add(Label("外观、行为与提醒会回到初始状态，清理记录不会受影响。",
                        11, color=self.tm.theme.muted, parent=modal))
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        cancel = GlassButton("取消", "secondary", None, modal, height=44)
        cancel.clicked.connect(modal.close_modal)
        buttons.addWidget(cancel, 1)
        reset = GlassButton("恢复默认", "danger", "settings", modal, height=44)
        reset.clicked.connect(lambda: self._reset_settings(modal))
        buttons.addWidget(reset, 1)
        modal.add_layout(buttons)
        self._show_modal(modal)

    def _reset_settings(self, modal: GlassModal) -> None:
        self.store.data = Settings()
        self.store.save()
        self.settings = self.store.data
        self.tm.set_mode("auto")
        try:
            from system_utils import set_startup, set_weekly_reminder
            set_startup(False)
            set_weekly_reminder(False)
        except Exception:
            pass
        self.settings_page.sync_from_store()
        modal.close_modal()
        self.show_toast("已恢复默认设置。")

    def _confirm_quit(self) -> None:
        modal = self._new_modal(430)
        modal.add(Label("要让清理专家休息了吗？", 21, QFont.Weight.Bold, parent=modal,
                        display=True))
        modal.add(Label("软件会完全退出；如果只是想让出桌面，可以最小化到托盘。",
                        11, color=self.tm.theme.muted, parent=modal))
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        cancel = GlassButton("继续使用", "secondary", None, modal, height=44)
        cancel.clicked.connect(modal.close_modal)
        buttons.addWidget(cancel, 1)
        exit_btn = GlassButton("退出软件", "danger", "power", modal, height=44)
        exit_btn.clicked.connect(self._quit_app)
        buttons.addWidget(exit_btn, 1)
        modal.add_layout(buttons)
        self._show_modal(modal)

    # ------------------------------------------------------------------ tray
    def _build_tray(self) -> None:
        self.tray: Optional[TrayController] = None
        self._qt_tray: Optional[QSystemTrayIcon] = None
        self._tray_bridge = TrayBridge()
        self._tray_bridge.open_requested.connect(self._show_from_tray)
        self._tray_bridge.scan_requested.connect(self._scan_from_tray)
        self._tray_bridge.quit_requested.connect(self._quit_app)
        icon_path = self._resource("assets/app_icon.png")
        if pystray_available():
            controller = TrayController(
                icon_path,
                lambda: self._tray_bridge.open_requested.emit(),
                lambda: self._tray_bridge.scan_requested.emit(),
                lambda: self._tray_bridge.quit_requested.emit(),
            )
            if controller.start():
                self.tray = controller
                QApplication.instance().setQuitOnLastWindowClosed(False)
                return
        # 兜底：pystray 在无托盘环境失败时，仍保证窗口可找回
        if QSystemTrayIcon.isSystemTrayAvailable():
            icon = QIcon(str(icon_path))
            tray = QSystemTrayIcon(icon, self)
            menu = QMenu()
            menu.addAction("打开主界面", self._show_from_tray)
            menu.addAction("立即扫描", self._scan_from_tray)
            menu.addSeparator()
            menu.addAction("退出", self._quit_app)
            tray.setContextMenu(menu)
            tray.setToolTip(APP_NAME)
            tray.activated.connect(lambda reason: self._show_from_tray()
                                   if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            tray.show()
            self._qt_tray = tray
            QApplication.instance().setQuitOnLastWindowClosed(False)

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _scan_from_tray(self) -> None:
        self._show_from_tray()
        self.start_scan("cleaner")

    def _quit_app(self) -> None:
        self._force_quit = True
        if self.scan_worker is not None:
            self.scan_worker.cancel()
        if self.clean_worker is not None:
            self.clean_worker.cancel()
        if self.tray is not None:
            self.tray.stop()
        if self._qt_tray is not None:
            self._qt_tray.hide()
        QApplication.instance().quit()

    # ------------------------------------------------------------------ helpers
    def show_toast(self, message: str, duration: int = 2800) -> None:
        self.toast.show_message(message, duration)

    def _open_recycle(self) -> None:
        from system_utils import open_recycle_bin
        open_recycle_bin()
        self.show_toast("已打开回收站。是否清空，请由你亲自决定。")

    def _relaunch_admin(self) -> None:
        if is_admin():
            self.show_toast("当前已经是管理员权限。")
            return
        if relaunch_as_admin():
            self._quit_app()
        else:
            self.show_toast("UAC 被取消，仍以普通权限运行。")

    def _apply_demo(self) -> None:
        from scanner import make_demo_result
        result = make_demo_result()
        self.clean_page.set_scan_result(result)
        self.files_page.set_scan_result(result)
        self.dashboard.set_scan_result(result)
        self.history_page.refresh()

    def window_action(self, kind: str) -> None:
        if kind == "close":
            self.close()
        elif kind == "min":
            self.showMinimized()
        elif kind == "max":
            if self.isMaximized():
                self.showNormal()
                self.root_layout.setContentsMargins(14, 14, 14, 14)
                self.shell.radius = 20
                self.shell.update()
            else:
                self.showMaximized()
                self.root_layout.setContentsMargins(0, 0, 0, 0)
                self.shell.radius = 0
                self.shell.update()

    def _theme_changed(self, *_args) -> None:
        self.update()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        # 不在界面内弹右键菜单，避免破坏简洁感
        event.ignore()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._force_quit:
            event.accept()
            return
        tray_active = self.tray is not None or self._qt_tray is not None
        if self.settings.close_to_tray and tray_active:
            event.ignore()
            self.hide()
            if not self._tray_notified:
                self._tray_notified = True
                if self.tray is not None:
                    self.tray.notify(APP_NAME, "已收起在托盘，需要时点击图标回来。")
                elif self._qt_tray is not None:
                    self._qt_tray.showMessage(APP_NAME, "已收起在托盘，需要时点击图标回来。",
                                              QSystemTrayIcon.MessageIcon.Information, 2500)
            return
        self._quit_app()
        event.accept()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_handles()
        if self.toast is not None:
            self.toast.reposition()
        if self._modal is not None and self._modal.isVisible():
            self._modal.setGeometry(self.shell.rect())

    def _layout_handles(self) -> None:
        if not hasattr(self, "_handles"):
            return
        margin = 6
        w = self.width()
        h = self.height()
        outer = 14
        for handle in self._handles:
            edges = handle.edges
            left = edges & Qt.Edge.LeftEdge
            right = edges & Qt.Edge.RightEdge
            top = edges & Qt.Edge.TopEdge
            bottom = edges & Qt.Edge.BottomEdge
            if left and top:
                geo = QRect(0, 0, outer + 10, outer + 10)
            elif right and top:
                geo = QRect(w - outer - 10, 0, outer + 10, outer + 10)
            elif left and bottom:
                geo = QRect(0, h - outer - 10, outer + 10, outer + 10)
            elif right and bottom:
                geo = QRect(w - outer - 10, h - outer - 10, outer + 10, outer + 10)
            elif left:
                geo = QRect(0, outer, margin + 6, h - outer * 2)
            elif right:
                geo = QRect(w - margin - 6, outer, margin + 6, h - outer * 2)
            elif top:
                geo = QRect(outer, 0, w - outer * 2, margin + 6)
            else:
                geo = QRect(outer, h - margin - 6, w - outer * 2, margin + 6)
            handle.setGeometry(geo)
            handle.show()
            handle.raise_()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isMaximized():
            r = QRectF(self.shell.geometry()).adjusted(0.5, 0.5, -0.5, -0.5)
            draw_shadow(p, r, 20, QColor(self.tm.theme.shadow), spread=22,
                        y_offset=10, strength=0.9)


class AuroraShell(QWidget):
    """主窗口内的圆角背景；与 AuroraBackground 共用绘制逻辑。"""

    def __init__(self, theme_manager: ThemeManager, radius: int = 20,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tm = theme_manager
        self.radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        # 复用 AuroraBackground 的绘制实现
        from ui.glass import AuroraBackground
        self._painter = AuroraBackground(theme_manager, self, radius)
        self._painter.hide()
        self.tm.changed.connect(self.update)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._painter.setGeometry(self.rect())

    def paintEvent(self, event) -> None:  # noqa: N802
        # 直接内联一份相同语法，避免子控件被隐藏时无法渲染
        from ui.glass import noise_image
        t = self.tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(r), self.radius, self.radius)
        p.setClipPath(clip)
        grad = QLinearGradient(0, 0, r.width() * 0.2, r.height())
        grad.setColorAt(0, t.bg_top)
        grad.setColorAt(0.58, t.bg_bottom)
        grad.setColorAt(1, t.bg_bottom)
        p.fillRect(r, grad)
        from PySide6.QtGui import QRadialGradient
        if t.is_dark:
            self._radial(p, r.width() * 0.22, r.height() * 0.08, r.width() * 0.55, t.glow_violet, 118)
            self._radial(p, r.width() * 0.88, r.height() * 0.8, r.width() * 0.44, t.glow_cyan, 50)
            self._radial(p, r.width() * 0.66, r.height() * 0.15, r.width() * 0.34, t.glow_warm, 42)
        else:
            self._radial(p, r.width() * 0.15, -10, r.width() * 0.5, t.glow_warm, 112)
            self._radial(p, r.width() * 0.92, r.height() * 0.08, r.width() * 0.4, t.glow_violet, 60)
            self._radial(p, r.width() * 0.74, r.height() * 0.9, r.width() * 0.36, t.glow_cyan, 36)
        p.setOpacity(0.2 if t.is_dark else 0.16)
        p.setBrushOrigin(0, 0)
        from PySide6.QtGui import QBrush
        p.fillRect(r, QBrush(noise_image(t.is_dark)))
        p.setOpacity(1)
        v = QRadialGradient(r.width() / 2, r.height() / 2, max(r.width(), r.height()) * 0.82)
        v.setColorAt(0.5, QColor(0, 0, 0, 0))
        v.setColorAt(1, QColor(0, 0, 0, 38 if t.is_dark else 12))
        p.fillRect(r, v)
        p.setPen(QPen(QColor(255, 255, 255, 45 if t.is_dark else 120), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), self.radius, self.radius)

    @staticmethod
    def _radial(p: QPainter, x: float, y: float, radius: float, color: QColor, alpha: int) -> None:
        from PySide6.QtGui import QRadialGradient
        c = QColor(color); c.setAlpha(alpha)
        grad = QRadialGradient(x, y, radius)
        grad.setColorAt(0, c)
        c2 = QColor(color); c2.setAlpha(max(0, alpha // 3))
        grad.setColorAt(0.55, c2)
        c3 = QColor(color); c3.setAlpha(0)
        grad.setColorAt(1, c3)
        p.fillRect(QRectF(x - radius, y - radius, radius * 2, radius * 2), grad)


def result_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    return f"{int(seconds // 60)} 分 {int(seconds % 60)} 秒"
