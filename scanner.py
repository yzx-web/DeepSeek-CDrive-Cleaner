# -*- coding: utf-8 -*-
"""智能扫描引擎：8 类垃圾 + 大文件体检。

扫描在 QThread 中执行，类别任务并发；每个类别通过信号把文件数、体积实时
送回 UI。任何异常都被收敛为该类别的错误，不会让整个扫描崩掉。
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from PySide6.QtCore import QObject, QThread, Signal

IS_WINDOWS = platform.system() == "Windows"
USER_HOME = Path.home()
LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", USER_HOME / "AppData" / "Local"))
WINDOWS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows" if IS_WINDOWS else "/tmp"))
SYSTEM_DRIVE = Path(os.environ.get("SystemDrive", "C:") + "\\") if IS_WINDOWS else Path("/")


# ---------------------------------------------------------------------------
# 类别定义
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CategoryDef:
    key: str
    name: str
    icon: str
    color_key: str
    title: str
    description: str
    tip: str
    default_selected: bool = True
    protected: bool = False


CATEGORIES: List[CategoryDef] = [
    CategoryDef(
        "temp", "Windows 临时文件", "folder", "temp", "临时文件",
        "系统与应用的中转站，清掉后程序和系统会自己重建。",
        "临时文件：软件运行时随手放下的草稿纸。关闭软件后基本没用，不会影响你的照片、文档或正在运行的程序。",
    ),
    CategoryDef(
        "recycle", "回收站", "trash", "recycle", "回收站",
        "你最近删除的东西都暂存在这里，本软件不会替你永久清空。",
        "回收站：删除文件的最后一道防线。为了守住「可撤销」，这里只做统计与提醒，请在系统中亲自确认后再清空。",
        default_selected=False, protected=True,
    ),
    CategoryDef(
        "update", "Windows 更新缓存", "download", "update", "更新缓存",
        "已经安装完成的更新安装包，删掉后系统需要时会重新下载。",
        "Windows 更新缓存：系统下载更新时留下的安装包。已经装好的更新不需要它们；以后需要时会重新下载，不影响当前系统。",
    ),
    CategoryDef(
        "thumbnail", "缩略图缓存", "photo", "thumbnail", "缩略图",
        "图片和视频的预览小图，删除后下次浏览会自动重新生成。",
        "缩略图缓存：资源管理器为了让你快速看到图片预览而存的小图。删除后第一次打开文件夹会稍慢，几秒后恢复。",
    ),
    CategoryDef(
        "prefetch", "预取文件 Prefetch", "bolt", "prefetch", "预取文件",
        "Windows 为加速启动留下的缓存，删除后下次启动会稍慢几秒。",
        "预取文件：Windows 记住你常打开哪些软件，提前把它们准备好。删除后下次启动会慢几秒，不影响任何功能。",
    ),
    CategoryDef(
        "browser", "浏览器缓存", "globe", "browser", "浏览器缓存",
        "只清理网页缓存与 GPU 缓存，密码、Cookie、书签、历史记录一概不碰。",
        "浏览器缓存：网页为了打开更快临时保存的图片和脚本。清掉只会让常用网站首次加载稍慢，不会退出登录，也不会丢收藏。",
        default_selected=False,
    ),
    CategoryDef(
        "logs", "系统日志与错误转储", "doc", "logs", "日志与转储",
        "已经写完的系统日志和崩溃记录；正在使用的文件会自动跳过。",
        "系统日志与转储：系统写下的“日记”和出错时的现场快照。旧的可以清，正在写入的会自动跳过；不影响系统运行。",
    ),
    CategoryDef(
        "bigfiles", "大文件体检", "search", "bigfiles", "大文件体检",
        "C 盘用户目录中超过 500MB 的文件，逐项确认后才会处理。",
        "大文件体检：不是垃圾，而是可能占地方的视频、压缩包或镜像。删除同样进入回收站；请确认是你不再需要的文件。",
        default_selected=False,
    ),
]

CATEGORY_MAP: Dict[str, CategoryDef] = {c.key: c for c in CATEGORIES}
BIG_FILE_MIN = 500 * 1024 * 1024


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass
class FileEntry:
    path: Path
    size: int
    modified: float = 0.0


@dataclass
class CategoryResult:
    key: str
    files: List[FileEntry] = field(default_factory=list)
    total_size: int = 0
    skipped: int = 0
    error: str = ""
    elapsed: float = 0.0
    scanned_count: int = 0

    @property
    def count(self) -> int:
        return len(self.files)

    @property
    def defn(self) -> CategoryDef:
        return CATEGORY_MAP[self.key]


@dataclass
class DiskStats:
    total: int
    used: int
    free: int

    @property
    def used_ratio(self) -> float:
        return self.used / self.total if self.total else 0.0

    @property
    def health_text(self) -> str:
        ratio = self.used_ratio
        if ratio >= 0.9:
            return "需要护理"
        if ratio >= 0.78:
            return "有点偏胖"
        if ratio >= 0.62:
            return "良好"
        return "很健康"


@dataclass
class ScanResult:
    categories: Dict[str, CategoryResult]
    disk: DiskStats
    started_at: float
    elapsed: float
    cancelled: bool = False
    errors: List[str] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(r.total_size for r in self.categories.values())

    @property
    def total_count(self) -> int:
        return sum(r.count for r in self.categories.values())

    @property
    def selected_size(self) -> int:
        return sum(r.total_size for r in self.categories.values()
                   if r.defn.default_selected and not r.defn.protected)

    @property
    def selected_count(self) -> int:
        return sum(r.count for r in self.categories.values()
                   if r.defn.default_selected and not r.defn.protected)


def get_disk_stats() -> DiskStats:
    try:
        usage = shutil.disk_usage(str(SYSTEM_DRIVE))
        return DiskStats(total=usage.total, used=usage.used, free=usage.free)
    except Exception:
        return DiskStats(total=0, used=0, free=0)


def _iter_files(root: Path, cancel: threading.Event, should_include: Optional[Callable[[Path], bool]] = None,
                max_depth: int = 18, on_file: Optional[Callable[[Path, int], None]] = None) -> Iterable[Path]:
    """安全遍历：不跟随符号链接，不进入回收站/系统卷目录，可随时中断。"""
    if not root.exists():
        return
    base_depth = len(root.parts)
    try:
        stack: List[Path] = [root]
        while stack:
            if cancel.is_set():
                return
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        if cancel.is_set():
                            return
                        try:
                            if entry.is_symlink() or bool(getattr(entry, "is_junction", lambda: False)()):
                                continue
                        except Exception:
                            continue
                        name_lower = entry.name.lower()
                        if entry.is_dir(follow_symlinks=False):
                            if name_lower in {"$recycle.bin", "system volume information"}:
                                continue
                            if len(Path(entry.path).parts) - base_depth >= max_depth:
                                continue
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            path = Path(entry.path)
                            if should_include is not None and not should_include(path):
                                continue
                            if on_file is not None:
                                on_file(path, 0)
                            yield path
            except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
                continue
    except Exception:
        return


def _file_size(path: Path) -> int:
    try:
        if path.is_symlink():
            return 0
        return path.stat().st_size
    except (OSError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# 各类别探测器
# ---------------------------------------------------------------------------
def _scan_temp(cancel: threading.Event, progress: Callable[[int, int], None]) -> CategoryResult:
    roots = {WINDOWS_DIR / "Temp", Path(os.environ.get("TEMP", "")) if os.environ.get("TEMP") else None}
    roots = {r for r in roots if r is not None and str(r)}
    seen: Set[str] = set()
    result = CategoryResult("temp")
    for root in roots:
        for path in _iter_files(root, cancel, max_depth=8):
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            size = _file_size(path)
            result.files.append(FileEntry(path, size, path.stat().st_mtime if path.exists() else 0))
            result.total_size += size
            if len(result.files) % 60 == 0:
                progress(result.count, result.total_size)
            if cancel.is_set():
                break
    progress(result.count, result.total_size)
    return result


def _scan_recycle(cancel: threading.Event, progress: Callable[[int, int], None]) -> CategoryResult:
    result = CategoryResult("recycle")
    if not IS_WINDOWS:
        return result
    try:
        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("i64Size", ctypes.c_longlong),
                        ("i64NumItems", ctypes.c_longlong)]

        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(info)
        # SHQueryRecycleBinW(None, ...) 统计当前用户的回收站，无需管理员权限
        hres = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if hres == 0:
            result.total_size = int(info.i64Size)
            result.scanned_count = int(info.i64NumItems)
    except Exception as exc:
        result.error = str(exc)
    progress(result.scanned_count, result.total_size)
    return result


def _scan_update(cancel: threading.Event, progress: Callable[[int, int], None]) -> CategoryResult:
    result = CategoryResult("update")
    root = WINDOWS_DIR / "SoftwareDistribution" / "Download"
    for path in _iter_files(root, cancel, max_depth=10):
        size = _file_size(path)
        result.files.append(FileEntry(path, size, path.stat().st_mtime if path.exists() else 0))
        result.total_size += size
        if len(result.files) % 40 == 0:
            progress(result.count, result.total_size)
    progress(result.count, result.total_size)
    return result


def _scan_thumbnail(cancel: threading.Event, progress: Callable[[int, int], None]) -> CategoryResult:
    result = CategoryResult("thumbnail")
    explorer = LOCAL_APP_DATA / "Microsoft" / "Windows" / "Explorer"
    if not explorer.exists():
        return result
    try:
        for entry in os.scandir(explorer):
            if cancel.is_set():
                break
            path = Path(entry.path)
            name = entry.name.lower()
            # 只收 thumbcache_*.db / iconcache_*.db，绝不碰其他 Explorer 数据
            if entry.is_file(follow_symlinks=False) and (
                    (name.startswith("thumbcache_") and name.endswith(".db")) or
                    (name.startswith("iconcache_") and name.endswith(".db"))):
                size = _file_size(path)
                result.files.append(FileEntry(path, size, path.stat().st_mtime))
                result.total_size += size
    except (PermissionError, OSError) as exc:
        result.error = str(exc)
    progress(result.count, result.total_size)
    return result


def _scan_prefetch(cancel: threading.Event, progress: Callable[[int, int], None]) -> CategoryResult:
    result = CategoryResult("prefetch")
    root = WINDOWS_DIR / "Prefetch"
    for path in _iter_files(root, cancel, max_depth=2,
                            should_include=lambda p: p.suffix.lower() in {".pf"}):
        size = _file_size(path)
        result.files.append(FileEntry(path, size, path.stat().st_mtime if path.exists() else 0))
        result.total_size += size
    progress(result.count, result.total_size)
    return result


def browser_cache_roots() -> List[Path]:
    """只返回缓存目录，绝不返回 User Data、Cookies、History 所在层级。"""
    roots: List[Path] = []
    browsers = [
        LOCAL_APP_DATA / "Microsoft" / "Edge" / "User Data",
        LOCAL_APP_DATA / "Google" / "Chrome" / "User Data",
        LOCAL_APP_DATA / "BraveSoftware" / "Brave-Browser" / "User Data",
    ]
    for user_data in browsers:
        if not user_data.exists():
            continue
        candidates = [user_data / "Default"]
        try:
            candidates += [p for p in user_data.iterdir()
                           if p.is_dir() and p.name.startswith("Profile ")]
        except Exception:
            pass
        for profile in candidates:
            for cache_name in ("Cache", "Code Cache", "GPUCache", "DawnCache", "ShaderCache"):
                path = profile / cache_name
                if path.exists() and path.is_dir():
                    roots.append(path)
    return roots


def _scan_browser(cancel: threading.Event, progress: Callable[[int, int], None]) -> CategoryResult:
    result = CategoryResult("browser")
    for root in browser_cache_roots():
        for path in _iter_files(root, cancel, max_depth=10):
            size = _file_size(path)
            result.files.append(FileEntry(path, size, path.stat().st_mtime if path.exists() else 0))
            result.total_size += size
            if len(result.files) % 80 == 0:
                progress(result.count, result.total_size)
        if cancel.is_set():
            break
    progress(result.count, result.total_size)
    return result


def _scan_logs(cancel: threading.Event, progress: Callable[[int, int], None]) -> CategoryResult:
    result = CategoryResult("logs")
    roots = [
        WINDOWS_DIR / "Logs",
        WINDOWS_DIR / "Minidump",
        LOCAL_APP_DATA / "CrashDumps",
    ]
    memory_dump = WINDOWS_DIR / "MEMORY.DMP"
    suffixes = {".log", ".tmp", ".old", ".dmp", ".etl"}
    if memory_dump.exists() and memory_dump.is_file():
        try:
            size = memory_dump.stat().st_size
            result.files.append(FileEntry(memory_dump, size, memory_dump.stat().st_mtime))
            result.total_size += size
        except OSError:
            pass
    for root in roots:
        for path in _iter_files(root, cancel, max_depth=6,
                                should_include=lambda p: p.suffix.lower() in suffixes):
            size = _file_size(path)
            result.files.append(FileEntry(path, size, path.stat().st_mtime if path.exists() else 0))
            result.total_size += size
            if len(result.files) % 30 == 0:
                progress(result.count, result.total_size)
    progress(result.count, result.total_size)
    return result


def _scan_bigfiles(cancel: threading.Event, progress: Callable[[int, int], None]) -> CategoryResult:
    result = CategoryResult("bigfiles")
    if not IS_WINDOWS:
        return result
    excluded = {"appdata", "application data", "local settings", "onedrive", "$recycle.bin",
                "node_modules", ".git", ".cache", "windows", "program files", "program files (x86)"}
    seen = 0

    def on_file(path: Path, _size: int) -> None:
        nonlocal seen
        seen += 1
        if seen % 150 == 0:
            progress(seen, result.total_size)

    for path in _iter_files(USER_HOME, cancel, max_depth=9, on_file=on_file):
        if cancel.is_set():
            break
        try:
            rel_parts = {part.lower() for part in path.relative_to(USER_HOME).parts[:-1]}
        except Exception:
            rel_parts = set()
        if rel_parts & excluded:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size >= BIG_FILE_MIN:
            result.files.append(FileEntry(path, size, path.stat().st_mtime))
            result.total_size += size
            progress(seen, result.total_size)
    result.scanned_count = seen
    # 体积从大到小，用户先看到最占地方的
    result.files.sort(key=lambda f: f.size, reverse=True)
    return result


SCANNERS: Dict[str, Callable[[threading.Event, Callable[[int, int], None]], CategoryResult]] = {
    "temp": _scan_temp,
    "recycle": _scan_recycle,
    "update": _scan_update,
    "thumbnail": _scan_thumbnail,
    "prefetch": _scan_prefetch,
    "browser": _scan_browser,
    "logs": _scan_logs,
    "bigfiles": _scan_bigfiles,
}


# ---------------------------------------------------------------------------
# 线程化扫描
# ---------------------------------------------------------------------------
class ScanSignals(QObject):
    category_started = Signal(str)
    category_progress = Signal(str, int, int)       # key, count, bytes
    category_done = Signal(object)                  # CategoryResult
    overall = Signal(float, str, int, int)          # 0~1, label, count, bytes
    finished = Signal(object)                       # ScanResult
    failed = Signal(str)
    cancelled = Signal()


class ScanWorker(QThread):
    """扫描调度器：类别并发执行，主线程只收信号。"""

    def __init__(self, categories: Optional[List[str]] = None,
                 max_workers: int = 4, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.signals = ScanSignals()
        self.keys = categories or [c.key for c in CATEGORIES]
        self.max_workers = max(1, max_workers)
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._completed = 0
        self._total_count = 0
        self._total_bytes = 0
        self._last_emit = 0.0

    def cancel(self) -> None:
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def _emit_progress(self, current_key: str, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit < 0.12:
            return
        self._last_emit = now
        with self._lock:
            completed = self._completed
            count = self._total_count
            size = self._total_bytes
        total = max(1, len(self.keys))
        # 进行中的类别占一半权重，避免从 0 直接跳到 12.5%
        progress = min(0.985, (completed + 0.24) / total) if completed < total else 1.0
        self.signals.overall.emit(progress, current_key, count, size)

    def _run_category(self, key: str) -> CategoryResult:
        start = time.monotonic()
        self.signals.category_started.emit(key)
        started_emit = time.monotonic()
        last_emit = [0.0]

        def progress(count: int, size: int) -> None:
            now = time.monotonic()
            if now - last_emit[0] > 0.15 or count == 0:
                last_emit[0] = now
                self.signals.category_progress.emit(key, count, size)
                with self._lock:
                    self._total_count = max(self._total_count, count)
                    self._total_bytes = max(self._total_bytes, size)
                self._emit_progress(key)

        try:
            result = SCANNERS[key](self._cancel, progress)
        except Exception as exc:
            result = CategoryResult(key=key, error=f"{type(exc).__name__}: {exc}")
        result.elapsed = time.monotonic() - start
        with self._lock:
            self._completed += 1
            self._total_count += result.count
            self._total_bytes += result.total_size
        self.signals.category_done.emit(result)
        self._emit_progress(key, force=True)
        return result

    def run(self) -> None:
        started = time.monotonic()
        disk = get_disk_stats()
        results: Dict[str, CategoryResult] = {}
        self.signals.overall.emit(0.01, "准备扫描", 0, 0)
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="scan") as pool:
                futures = {pool.submit(self._run_category, key): key for key in self.keys}
                for future in as_completed(futures):
                    if self._cancel.is_set():
                        continue
                    key = futures[future]
                    try:
                        results[key] = future.result()
                    except Exception as exc:
                        results[key] = CategoryResult(key=key, error=str(exc))
            if self._cancel.is_set():
                self.signals.cancelled.emit()
                return
            for key in self.keys:
                if key not in results:
                    results[key] = CategoryResult(key=key, error="扫描未完成")
            errors = [f"{r.defn.name}：{r.error}" for r in results.values() if r.error]
            final = ScanResult(results, disk, started, time.monotonic() - started,
                               cancelled=False, errors=errors)
            self.signals.overall.emit(1.0, "扫描完成", final.total_count, final.total_size)
            self.signals.finished.emit(final)
        except Exception as exc:
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# 演示数据（仅用于 UI 预览，真实 exe 默认不启用）
# ---------------------------------------------------------------------------
def make_demo_result() -> ScanResult:
    """生成一组可信的演示扫描结果，供低权限开发环境预览界面。"""
    now = time.time()
    sizes = {
        "temp": [5.4, 2.1, 0.8, 12.7, 0.4, 7.3, 0.2, 1.1],
        "recycle": [],
        "update": [12.8, 9.4, 3.2, 26.5],
        "thumbnail": [3.4, 1.8, 0.9, 2.2, 1.1],
        "prefetch": [1.8, 1.2, 0.7, 2.4, 0.9, 1.5, 0.6],
        "browser": [8.9, 14.2, 6.7, 22.1, 3.8, 11.5, 5.2],
        "logs": [2.6, 0.8, 1.1, 18.6, 0.3, 0.7],
        "bigfiles": [1180.0, 890.0, 642.0, 532.0],
    }
    cats: Dict[str, CategoryResult] = {}
    for key in sizes:
        result = CategoryResult(key=key)
        if key == "recycle":
            result.total_size = int(2.65 * 1024 ** 3)
            result.scanned_count = 184
        elif key == "bigfiles":
            for i, mb in enumerate(sizes[key]):
                path = USER_HOME / ("Videos" if i % 2 == 0 else "Download") / f"大文件_{i + 1}.mp4"
                size = int(mb * 1024 ** 2)
                result.files.append(FileEntry(path, size, now - (i + 1) * 86400 * 23))
                result.total_size += size
        else:
            for i, mb in enumerate(sizes[key]):
                path = WINDOWS_DIR / "Temp" / f"{key}_cache_{i + 1}.dat"
                size = int(mb * 1024 ** 2)
                result.files.append(FileEntry(path, size, now - (i + 1) * 3600))
                result.total_size += size
        cats[key] = result
    disk = DiskStats(total=512 * 1024 ** 3, used=398 * 1024 ** 3, free=114 * 1024 ** 3)
    return ScanResult(cats, disk, now - 18.4, 18.4, errors=[])
