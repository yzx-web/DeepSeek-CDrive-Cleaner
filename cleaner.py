# -*- coding: utf-8 -*-
"""安全清理器：白名单校验 + 回收站删除 + 占用跳过。

安全底线
--------
1. 绝不永久删除：每个文件都通过 send2trash 调用系统 IFileOperation 放入回收站。
2. 绝不静默删除：清理前必须由界面二次确认，勾选结果与文件列表 100% 对应。
3. 绝不越界：每个路径先经过 realpath + 白名单 + 敏感文件多重校验。
4. 绝不中断：单个文件被占用/权限不足时记录原因并继续，最终统一汇报。
"""
from __future__ import annotations

import os
import platform
import re
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import QObject, QThread, Signal
from send2trash import send2trash

from app_settings import APP_SLUG, data_dir
from scanner import (BIG_FILE_MIN, CATEGORY_MAP, CategoryResult, FileEntry,
                     LOCAL_APP_DATA, SYSTEM_DRIVE, USER_HOME, WINDOWS_DIR,
                     browser_cache_roots)

IS_WINDOWS = platform.system() == "Windows"


# ---------------------------------------------------------------------------
# 白名单
# ---------------------------------------------------------------------------
# 下面每一项都是“只允许清理”的根目录，逐行写清用途与安全依据。
# 校验时使用 realpath 解析后的路径做前缀匹配，杜绝 ../ 或符号链接逃逸。
def whitelist_roots() -> List[Tuple[Path, str, str]]:
    roots: List[Tuple[Path, str, str]] = [
        # Windows 系统临时目录：系统与安装程序的中转文件，删后自动重建。
        (WINDOWS_DIR / "Temp", "temp", "系统临时文件根目录"),
        # 当前用户临时目录：Office、浏览器安装器等留下的临时文件，不含用户文档。
        (Path(os.environ.get("TEMP", str(LOCAL_APP_DATA / "Temp"))), "temp", "用户临时文件根目录"),
        # Windows Update 下载缓存：只清理已下载的更新包，不动已安装的系统组件。
        (WINDOWS_DIR / "SoftwareDistribution" / "Download", "update", "更新安装包缓存"),
        # 缩略图数据库所在目录：后续还会按 thumbcache_*.db / iconcache_*.db 精确限定文件名。
        (LOCAL_APP_DATA / "Microsoft" / "Windows" / "Explorer", "thumbnail", "缩略图数据库目录"),
        # Prefetch：仅允许 .pf 文件，绝不清理该目录中其他系统数据。
        (WINDOWS_DIR / "Prefetch", "prefetch", "预取缓存目录"),
        # 系统日志目录：仅允许 .log/.tmp/.old/.dmp/.etl，且文件必须已可读。
        (WINDOWS_DIR / "Logs", "logs", "系统日志目录"),
        # 崩溃转储目录：只清 minidump/MEMORY.DMP，用于事后排障，删除不影响运行。
        (WINDOWS_DIR / "Minidump", "logs", "小型崩溃转储目录"),
        # 用户崩溃转储：只清 CrashDumps 下的 .dmp，不碰其他 AppData 数据。
        (LOCAL_APP_DATA / "CrashDumps", "logs", "用户崩溃转储目录"),
    ]
    # 浏览器缓存根目录来自精确的 Cache / Code Cache / GPUCache 列表。
    # 不包含 User Data 顶层，因此 Cookies、Login Data、History、Bookmarks 永远进不来。
    for cache in browser_cache_roots():
        roots.append((cache, "browser", "浏览器缓存目录（仅 Cache 类）"))
    return roots


# AppData 中可能存储用户数据的敏感目录，即使位于临时根下也不清理。
_PROTECTED_DIR_NAMES = {
    "desktop", "documents", "downloads", "pictures", "music", "videos",
    "onedrive", "dropbox", "icloud drive", "google drive",
}
# 浏览器隐私文件名称：无论出现在哪里，一律拒绝。
_SENSITIVE_NAMES = {
    "cookies", "cookies-journal", "login data", "login data for account",
    "login data-journal", "web data", "web data-journal", "history",
    "history-journal", "bookmarks", "bookmarks.bak", "preferences",
    "local state", "passwords", "affiliations", "top sites", "visits",
    "favicons", "network action predictor", "shortcuts", "sessions",
    "session storage", "local storage", "indexeddb", "extensions",
}
_LOG_SUFFIXES = {".log", ".tmp", ".old", ".dmp", ".etl"}


def _norm(path: Path) -> str:
    try:
        resolved = path.resolve(strict=False)
    except Exception:
        resolved = path.absolute()
    return os.path.normcase(os.path.normpath(str(resolved)))


def _is_within(child: str, parent: str) -> bool:
    if not child or not parent:
        return False
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False


@dataclass
class SafetyVerdict:
    safe: bool
    reason: str = ""


def validate_path(entry: FileEntry, category_key: str, allow_user_data: bool = False) -> SafetyVerdict:
    """逐层校验一个待删除文件。返回 safe + 可读的中文拒绝原因。"""
    path = Path(entry.path)
    if not path.exists():
        return SafetyVerdict(False, "文件已经不在了")
    try:
        if path.is_symlink() or path.is_dir():
            return SafetyVerdict(False, "符号链接或目录不会被清理")
    except OSError:
        return SafetyVerdict(False, "无法读取文件属性")
    if not path.is_file():
        return SafetyVerdict(False, "不是普通文件")

    # 名称级隐私保护（任何类别都生效）
    lower_name = path.name.lower()
    if lower_name in _SENSITIVE_NAMES:
        return SafetyVerdict(False, "属于浏览器隐私数据，已保护")
    if any(part.lower() in _PROTECTED_DIR_NAMES for part in path.parts):
        # 大文件体检是唯一例外，但只允许用户逐项勾选后的普通文件，仍走回收站。
        if not (category_key == "bigfiles" and allow_user_data):
            return SafetyVerdict(False, "属于用户资料目录，已保护")
    if any(part.lower() in {"appdata", "application data"} for part in path.parts) and category_key != "temp":
        return SafetyVerdict(False, "AppData 非缓存数据，已保护")
    # 不碰本软件自己的配置/历史，避免清理工具把自己清掉
    if APP_SLUG.lower() in lower_name or APP_SLUG.lower() in _norm(path).lower():
        if category_key != "temp":
            return SafetyVerdict(False, "属于清理工具自身数据，已保护")

    npath = _norm(path)
    if category_key == "recycle":
        # 回收站内容本来就在回收站中，清空即永久删除；本软件拒绝代为永久删除。
        return SafetyVerdict(False, "回收站需你亲自在系统中确认，本软件不代删")

    if category_key == "bigfiles":
        if not allow_user_data:
            return SafetyVerdict(False, "大文件需逐项明确勾选")
        if not _is_within(npath, _norm(USER_HOME)):
            return SafetyVerdict(False, "不在用户目录内")
        try:
            if path.stat().st_size < BIG_FILE_MIN:
                return SafetyVerdict(False, "体积已不足 500MB，重新扫描后再处理")
        except OSError:
            return SafetyVerdict(False, "无法读取文件大小")
        return SafetyVerdict(True)

    # 常规类别必须命中白名单根目录
    for root, root_category, _note in whitelist_roots():
        if root_category != category_key:
            continue
        nroot = _norm(root)
        if not _is_within(npath, nroot) or npath == nroot:
            continue
        lower_parts = [p.lower() for p in path.parts]
        if "cache" not in lower_parts and "code cache" not in lower_parts and \
                "gpucache" not in lower_parts and "dawncache" not in lower_parts and \
                "shadercache" not in lower_parts and category_key == "browser":
            continue
        if category_key == "thumbnail":
            if not re.match(r"^(thumbcache|iconcache)_[0-9a-f]+\.db$", lower_name):
                continue
        if category_key == "prefetch" and path.suffix.lower() != ".pf":
            continue
        if category_key == "logs" and path.suffix.lower() not in _LOG_SUFFIXES:
            continue
        if category_key != "browser" and category_key != "temp":
            # 这些目录下若出现用户目录名，直接拒绝（例如 C:\Windows\Temp\Desktop\...）
            if any(part.lower() in _PROTECTED_DIR_NAMES for part in path.parts):
                return SafetyVerdict(False, "疑似用户资料目录，已保护")
        return SafetyVerdict(True)

    # 兜底拒绝：不在任何白名单根目录中的文件绝不能清理
    return SafetyVerdict(False, "不在安全白名单内")


# ---------------------------------------------------------------------------
# 清理执行
# ---------------------------------------------------------------------------
@dataclass
class SkippedItem:
    path: Path
    reason: str


@dataclass
class CleanResult:
    deleted_count: int = 0
    freed_bytes: int = 0
    skipped: List[SkippedItem] = field(default_factory=list)
    by_category: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    started_at: float = 0.0
    elapsed: float = 0.0
    cancelled: bool = False
    errors: List[str] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def busy_count(self) -> int:
        return sum(1 for item in self.skipped if "占用" in item.reason or "使用" in item.reason)


def _reason_for_error(exc: BaseException) -> str:
    text = str(exc)
    winerror = getattr(exc, "winerror", None)
    if winerror in (32, 33) or "being used" in text.lower() or "另一个程序" in text:
        return "文件正在被使用，已跳过"
    if isinstance(exc, PermissionError) or winerror == 5 or "Access is denied" in text:
        return "权限不足，已跳过"
    if isinstance(exc, FileNotFoundError):
        return "文件已经不在了"
    if "too long" in text.lower():
        return "路径过长，已跳过"
    return f"系统拒绝删除（{text[:60]}）"


class CleanSignals(QObject):
    progress = Signal(int, int, int, str)  # done, total, freed, current_name
    category_done = Signal(str, int, int)
    finished = Signal(object)
    failed = Signal(str)


class CleanWorker(QThread):
    """在后台线程执行回收站删除，保证 UI 50fps 不卡顿。"""

    def __init__(self, categories: List[CategoryResult], allow_big_files: bool = True,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.categories = categories
        self.allow_big_files = allow_big_files
        self.signals = CleanSignals()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        started = time.monotonic()
        result = CleanResult(started_at=started)
        all_entries: List[Tuple[CategoryResult, FileEntry]] = []
        for cat in self.categories:
            for entry in cat.files:
                all_entries.append((cat, entry))
        total = len(all_entries)
        done = 0
        skipped_by_cat: Dict[str, int] = {}
        for cat in self.categories:
            skipped_by_cat[cat.key] = 0
        if total == 0:
            result.elapsed = time.monotonic() - started
            self.signals.finished.emit(result)
            return

        for cat, entry in all_entries:
            if self._cancel.is_set():
                result.cancelled = True
                break
            done += 1
            name = entry.path.name
            if len(name) > 34:
                name = name[:16] + "…" + name[-14:]
            if done % 2 == 0 or done == total:
                self.signals.progress.emit(done, total, result.freed_bytes, name)
            verdict = validate_path(entry, cat.key,
                                    allow_user_data=(cat.key == "bigfiles" and self.allow_big_files))
            if not verdict.safe:
                result.skipped.append(SkippedItem(entry.path, verdict.reason))
                skipped_by_cat[cat.key] += 1
                continue
            try:
                # send2trash 在 Windows 上调用 IFileOperation，将文件移入系统回收站；
                # 在 Linux/macOS 上遵循系统垃圾箱规范。没有任何 os.remove/unlink 永久删除。
                send2trash(str(entry.path))
                result.deleted_count += 1
                result.freed_bytes += int(entry.size)
                old = result.by_category.get(cat.key, (0, 0))
                result.by_category[cat.key] = (old[0] + 1, old[1] + int(entry.size))
            except BaseException as exc:
                reason = _reason_for_error(exc)
                result.skipped.append(SkippedItem(entry.path, reason))
                skipped_by_cat[cat.key] += 1
        for cat in self.categories:
            deleted, freed = result.by_category.get(cat.key, (0, 0))
            self.signals.category_done.emit(cat.key, deleted, freed)
        result.elapsed = time.monotonic() - started
        result.cancelled = self._cancel.is_set()
        self.signals.finished.emit(result)
