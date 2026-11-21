# -*- coding: utf-8 -*-
"""DeepSeek v4.1 C盘清理专家 —— 程序入口。

启动顺序：
    高 DPI 策略 → QApplication → 主题管理器 → 主窗口 → 托盘
所有需要管理员权限的动作都不在启动时请求，只有用户明确触发时才走 UAC。
"""
from __future__ import annotations

import os
import platform
import sys
import traceback
from pathlib import Path

# Windows 任务栏图标分组（必须在 QApplication 创建前设置）
if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "DeepSeek.CDriveCleaner.4.1")
    except Exception:
        pass

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtGui import QIcon, QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from app_settings import APP_NAME, APP_VERSION, data_dir
from ui.theme import ThemeManager, set_app_font


def _resource(rel: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) / rel) if base else (Path(__file__).resolve().parent / rel)


def install_exception_hook() -> None:
    log = data_dir() / "error.log"

    def hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            log.write_text(text, encoding="utf-8")
        except Exception:
            pass
        try:
            QMessageBox.critical(None, "DeepSeek C盘清理专家",
                                 "程序遇到一个未预期的问题。\n\n"
                                 f"{exc_type.__name__}: {exc}\n\n"
                                 f"详细日志已保存到：{log}")
        except Exception:
            pass

    sys.excepthook = hook


def _selftest() -> int:
    """打包自检：不创建 GUI，只验证资源、依赖和模块能否加载。"""
    import json
    report = {"ok": False, "app": APP_NAME, "version": APP_VERSION}
    try:
        import PySide6
        from PIL import Image
        import pystray
        from send2trash import send2trash as _trash
        report["pyside6"] = PySide6.__version__
        from scanner import CATEGORIES
        report["categories"] = len(CATEGORIES)
        icon = _resource("assets/app_icon.png")
        report["icon"] = icon.exists()
        with Image.open(icon) as image:
            report["icon_size"] = list(image.size)
        from ui.main_window import MainWindow
        report["modules"] = "ok"
        report["ok"] = bool(report["icon"] and report["categories"] == 8)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    try:
        (data_dir() / "selftest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return 0 if report.get("ok") else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("DeepSeek C盘清理专家")
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("DeepSeek Tools")
    app.setWindowIcon(QIcon(str(_resource("assets/app_icon.png"))))
    app.setStyle("Fusion")
    try:
        app.setEffectEnabled(Qt.UIEffect.UI_AnimateMenu, True)
        app.setEffectEnabled(Qt.UIEffect.UI_FadeMenu, True)
    except Exception:
        pass

    theme = ThemeManager(app)
    set_app_font(app)
    install_exception_hook()

    from ui.main_window import MainWindow
    demo = os.environ.get("DEEPSEEK_DEMO", "0") == "1"
    remind = "--remind" in sys.argv
    startup_min = "--startup" in sys.argv and not remind
    window = MainWindow(demo=demo, remind=remind, startup_min=startup_min)
    # 保存引用，防止被 GC
    app._main_window = window  # type: ignore[attr-defined]
    if not startup_min:
        window.show()
    else:
        # 开机启动时先不打断用户；托盘可用则留在托盘
        if window.tray is None and window._qt_tray is None:
            window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
