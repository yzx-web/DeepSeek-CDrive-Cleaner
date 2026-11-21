# -*- coding: utf-8 -*-
"""本地设置与数据目录。

所有数据只保存在这台电脑的 %APPDATA%\\DeepSeekCleaner 下，不上传。
写入采用“临时文件 + 原子替换”，避免断电时把设置写坏。
"""
from __future__ import annotations

import json
import os
import platform
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Dict

APP_NAME = "DeepSeek v4.1 C盘清理专家"
APP_SLUG = "DeepSeekCleaner"
APP_VERSION = "4.1.0"


def data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_SLUG
    else:
        path = Path.home() / ".deepseekcleaner"
    path.mkdir(parents=True, exist_ok=True)
    return path


def desktop_dir() -> Path:
    """优先使用系统“桌面”已知文件夹，兼容 OneDrive 重定向。"""
    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(260)
            # CSIDL_DESKTOPDIRECTORY = 0x0010
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:
                return Path(buf.value)
        except Exception:
            pass
    path = Path.home() / "Desktop"
    if not path.exists():
        path = Path.home()
    return path


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


@dataclass
class Settings:
    theme: str = "auto"                    # auto / light / dark
    close_to_tray: bool = True
    startup: bool = False
    auto_shutdown: bool = False
    weekly_reminder: bool = False
    reduce_motion: bool = False
    last_clean_at: float = 0.0
    last_clean_bytes: int = 0
    onboarded: bool = False

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Settings":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in allowed})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SettingsStore:
    def __init__(self) -> None:
        self.path = data_dir() / "settings.json"
        self.data = Settings()
        self.load()

    def load(self) -> Settings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = Settings.from_dict(raw)
        except Exception:
            self.data = Settings()
        return self.data

    def save(self) -> None:
        atomic_write_json(self.path, self.data.to_dict())

    def set(self, key: str, value: Any) -> None:
        if hasattr(self.data, key):
            setattr(self.data, key, value)
            self.save()

    @property
    def history_path(self) -> Path:
        return data_dir() / "history.json"

    @property
    def log_path(self) -> Path:
        return data_dir() / "cleaner.log"
