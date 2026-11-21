# -*- coding: utf-8 -*-
"""Windows 系统集成：管理员权限、开机自启、计划任务、关机与资源路径。"""
from __future__ import annotations

import base64
import ctypes
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

IS_WINDOWS = platform.system() == "Windows"
PYSTRAY_AVAILABLE = True
try:
    import pystray
    from PIL import Image
except Exception:
    PYSTRAY_AVAILABLE = False


def resource_path(relative: str) -> Path:
    """兼容源码运行与 PyInstaller onefile 解包目录。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parent / relative


def is_admin() -> bool:
    if not IS_WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """以管理员身份重新启动。返回 False 表示用户取消了 UAC。"""
    if not IS_WINDOWS:
        return False
    try:
        if getattr(sys, "frozen", False):
            executable = sys.executable
            params = subprocess.list2cmdline(sys.argv[1:])
        else:
            executable = sys.executable
            params = subprocess.list2cmdline([str(Path(__file__).resolve().parents[1] / "main.py")] + sys.argv[1:])
        # 使用 ShellExecuteW + runas 弹出标准 UAC 提示
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params or None, None, 1
        )
        return int(result) > 32
    except Exception:
        return False


def set_startup(enabled: bool) -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        name = "DeepSeekC盘清理专家"
        if enabled:
            command = f'"{sys.executable}" --startup'
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def startup_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run")
        value, _ = winreg.QueryValueEx(key, "DeepSeekC盘清理专家")
        winreg.CloseKey(key)
        return bool(value)
    except Exception:
        return False


def set_weekly_reminder(enabled: bool) -> bool:
    """用 Windows 任务计划程序，每周日 10:00 启动软件提醒扫描。"""
    if not IS_WINDOWS:
        return False
    task_name = "DeepSeekCleanerWeekly"
    try:
        if enabled:
            exe = sys.executable
            cmd = f'"{exe}" --remind'
            result = subprocess.run(
                ["schtasks", "/Create", "/TN", task_name, "/TR", cmd,
                 "/SC", "WEEKLY", "/D", "SUN", "/ST", "10:00", "/F"],
                capture_output=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0
        subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"],
            capture_output=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def open_recycle_bin() -> None:
    try:
        if IS_WINDOWS:
            subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            subprocess.Popen(["xdg-open", str(Path.home())])
    except Exception:
        pass


def open_path(path: Path) -> None:
    try:
        if IS_WINDOWS:
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def show_in_explorer(path: Path) -> None:
    try:
        if IS_WINDOWS:
            subprocess.Popen(["explorer.exe", "/select,", str(path)],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            open_path(path.parent)
    except Exception:
        pass


def schedule_shutdown(seconds: int = 60) -> bool:
    if not IS_WINDOWS:
        return False
    try:
        subprocess.Popen(["shutdown", "/s", "/t", str(seconds)],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:
        return False


def cancel_shutdown() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        subprocess.run(["shutdown", "/a"], capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:
        return False


def can_restart_for_admin() -> bool:
    return IS_WINDOWS and not is_admin()


def pystray_available() -> bool:
    return PYSTRAY_AVAILABLE


class TrayController:
    """pystray 系统托盘，菜单：打开 / 立即扫描 / 退出。

    托盘运行在独立线程，所有回调通过 Qt Signal 安全地回到 UI 线程。
    """

    def __init__(self, icon_path: Path, open_cb, scan_cb, quit_cb) -> None:
        self.icon_path = icon_path
        self.open_cb = open_cb
        self.scan_cb = scan_cb
        self.quit_cb = quit_cb
        self.icon = None
        self._thread = None

    def start(self) -> bool:
        if not PYSTRAY_AVAILABLE:
            return False
        try:
            image = Image.open(self.icon_path).convert("RGBA")
            menu = pystray.Menu(
                pystray.MenuItem("打开主界面", lambda *_: self.open_cb(), default=True),
                pystray.MenuItem("立即扫描", lambda *_: self.scan_cb()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", lambda *_: self.quit_cb()),
            )
            self.icon = pystray.Icon("DeepSeekCleaner", image,
                                     "DeepSeek v4.1 C盘清理专家", menu)
            self._thread = __import__("threading").Thread(target=self.icon.run, daemon=True)
            self._thread.start()
            return True
        except Exception:
            self.icon = None
            return False

    def notify(self, title: str, message: str) -> None:
        try:
            if self.icon is not None:
                self.icon.notify(message, title)
        except Exception:
            pass

    def stop(self) -> None:
        try:
            if self.icon is not None:
                self.icon.stop()
        except Exception:
            pass
