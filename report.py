# -*- coding: utf-8 -*-
"""清理报告与本地历史。

报告使用纯文本（UTF-8 BOM 可选，Windows 记事本兼容），默认落在桌面。
历史只保存类别、体积、耗时和跳过数量，不保存任何文件内容。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app_settings import APP_NAME, APP_VERSION, atomic_write_json, data_dir, desktop_dir
from cleaner import CleanResult
from scanner import CATEGORY_MAP, ScanResult, get_disk_stats


def human_size(size: float) -> str:
    if not size or size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    if idx == 0:
        return f"{int(value)} B"
    return f"{value:.2f} {units[idx]}"


def human_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    return f"{minutes} 分 {sec} 秒"


@dataclass
class HistoryRecord:
    id: str
    timestamp: float
    freed_bytes: int
    deleted_count: int
    skipped_count: int
    elapsed: float
    categories: Dict[str, Dict[str, int]] = field(default_factory=dict)
    cancelled: bool = False

    @property
    def status(self) -> str:
        if self.cancelled:
            return "cancelled"
        if self.skipped_count > 0:
            return "partial"
        return "success"

    @property
    def status_text(self) -> str:
        return {"success": "清理成功", "partial": "部分跳过", "cancelled": "已取消"}[self.status]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "freed_bytes": self.freed_bytes,
            "deleted_count": self.deleted_count,
            "skipped_count": self.skipped_count,
            "elapsed": self.elapsed,
            "categories": self.categories,
            "cancelled": self.cancelled,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "HistoryRecord":
        return cls(
            id=str(raw.get("id", "")),
            timestamp=float(raw.get("timestamp", 0) or 0),
            freed_bytes=int(raw.get("freed_bytes", 0) or 0),
            deleted_count=int(raw.get("deleted_count", 0) or 0),
            skipped_count=int(raw.get("skipped_count", 0) or 0),
            elapsed=float(raw.get("elapsed", 0) or 0),
            categories=raw.get("categories", {}) or {},
            cancelled=bool(raw.get("cancelled", False)),
        )


class HistoryStore:
    def __init__(self, max_records: int = 80) -> None:
        self.path = data_dir() / "history.json"
        self.max_records = max_records
        self.records: List[HistoryRecord] = []
        self.load()

    def load(self) -> List[HistoryRecord]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw = raw.get("records", [])
            self.records = [HistoryRecord.from_dict(item) for item in raw if isinstance(item, dict)]
        except Exception:
            self.records = []
        self.records.sort(key=lambda r: r.timestamp, reverse=True)
        return self.records

    def save(self) -> None:
        payload = {"version": 1, "records": [r.to_dict() for r in self.records[:self.max_records]]}
        atomic_write_json(self.path, payload)

    def append(self, result: CleanResult, selected: List[str]) -> HistoryRecord:
        categories: Dict[str, Dict[str, int]] = {}
        for key, (deleted, freed) in result.by_category.items():
            categories[key] = {"deleted": deleted, "freed": freed}
        record = HistoryRecord(
            id=f"clean_{int(time.time() * 1000)}",
            timestamp=time.time(),
            freed_bytes=result.freed_bytes,
            deleted_count=result.deleted_count,
            skipped_count=result.skipped_count,
            elapsed=result.elapsed,
            categories=categories,
            cancelled=result.cancelled,
        )
        self.records.insert(0, record)
        self.records = self.records[:self.max_records]
        self.save()
        return record

    def clear(self) -> None:
        self.records = []
        self.save()


def build_report_text(result: CleanResult, selected: List[str]) -> str:
    now = dt.datetime.now()
    categories = []
    for key, (deleted, freed) in sorted(result.by_category.items(), key=lambda kv: kv[1][1], reverse=True):
        defn = CATEGORY_MAP.get(key)
        name = defn.name if defn else key
        categories.append(f"  • {name}：{deleted} 个文件 · {human_size(freed)}")
    if not categories:
        categories.append("  • 本次没有实际清理文件")
    skipped_lines = []
    for item in result.skipped[:40]:
        skipped_lines.append(f"  · {item.path.name}  —  {item.reason}")
    if len(result.skipped) > 40:
        skipped_lines.append(f"  · ……另有 {len(result.skipped) - 40} 项未逐条列出")
    if not skipped_lines:
        skipped_lines.append("  · 没有文件被跳过")
    disk = get_disk_stats()
    status = "已取消（部分完成）" if result.cancelled else "完成"
    text = f"""
{APP_NAME} · 清理报告
版本 {APP_VERSION}
生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本次释放：{human_size(result.freed_bytes)}
删除文件：{result.deleted_count} 个
跳过文件：{result.skipped_count} 个（其中被占用 {result.busy_count} 个）
耗时：{human_duration(result.elapsed)}
状态：{status}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

分类明细：
{chr(10).join(categories)}

跳过说明：
{chr(10).join(skipped_lines)}

C 盘当前状态：
  总容量：{human_size(disk.total)}
  已使用：{human_size(disk.used)}
  可用空间：{human_size(disk.free)}

安全说明：
  1. 本次清理的所有文件均通过 Windows 系统 API 移入回收站，可随时还原。
  2. 回收站类别未被本软件清空；它只做统计与提醒，避免不可恢复的数据丢失。
  3. 密码、Cookie、书签、历史记录、个人文档均未被触碰。
  4. 本软件不会上传任何文件、路径或使用数据。

—— {APP_NAME}
"让每一次清理，都有迹可循。"
"""
    return text.strip() + "\n"


def export_report(result: CleanResult, selected: List[str], folder: Optional[Path] = None) -> Path:
    target_dir = folder or desktop_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = target_dir / f"C盘清理报告_{stamp}.txt"
    if path.exists():
        path = target_dir / f"C盘清理报告_{stamp}_{int(time.time() % 1000):03d}.txt"
    # utf-8-sig 让 Windows 记事本正确识别中文
    path.write_text(build_report_text(result, selected), encoding="utf-8-sig")
    return path


def last_clean_summary() -> tuple[str, int]:
    store = HistoryStore()
    if not store.records:
        return "还没有清理过", 0
    rec = store.records[0]
    return dt.datetime.fromtimestamp(rec.timestamp).strftime("%m月%d日 %H:%M"), rec.freed_bytes


def build_record_text(record: HistoryRecord) -> str:
    now = dt.datetime.now()
    lines = []
    for key, info in sorted(record.categories.items(), key=lambda kv: kv[1].get("freed", 0), reverse=True):
        defn = CATEGORY_MAP.get(key)
        name = defn.name if defn else key
        lines.append(f"  • {name}：{info.get('deleted', 0)} 个文件 · {human_size(info.get('freed', 0))}")
    if not lines:
        lines.append("  • 本次没有实际清理文件")
    return f"""{APP_NAME} · 清理报告
版本 {APP_VERSION}
记录时间：{dt.datetime.fromtimestamp(record.timestamp).strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本次释放：{human_size(record.freed_bytes)}
删除文件：{record.deleted_count} 个
跳过文件：{record.skipped_count} 个
耗时：{human_duration(record.elapsed)}
状态：{record.status_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

分类明细：
{chr(10).join(lines)}

安全说明：
  所有清理文件均由系统 API 移入回收站；回收站类别没有被代为永久清空。
  密码、Cookie、书签、历史记录、个人文档均未被触碰。

—— {APP_NAME}
""".strip() + "\n"


def export_record(record: HistoryRecord, folder: Optional[Path] = None) -> Path:
    target_dir = folder or desktop_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.fromtimestamp(record.timestamp).strftime("%Y-%m-%d_%H%M%S")
    path = target_dir / f"C盘清理报告_{stamp}.txt"
    if path.exists():
        path = target_dir / f"C盘清理报告_{stamp}_{int(time.time() % 1000):03d}.txt"
    path.write_text(build_record_text(record), encoding="utf-8-sig")
    return path
