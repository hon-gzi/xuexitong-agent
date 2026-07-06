"""情景记忆 - 记录历史事件(工具执行结果等)"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# 数据文件路径(相对于项目根目录)
_EPISODES_FILE = Path("data/memory/episodes.jsonl")


class EpisodeStore:
    """持久化存储学习事件(刷课、作业等)。

    每行一条 JSON, 支持关键字搜索和过期清理。
    """

    def __init__(self, filepath: Path | None = None) -> None:
        self._filepath = filepath or _EPISODES_FILE
        # 确保目录存在
        self._filepath.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_episode(
        self,
        action: str,
        course: str,
        result: str,
        user_message: str,
    ) -> None:
        """在工具执行后自动记录一条事件。"""
        record: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "course": course,
            "result": result,
            "user_message": user_message,
        }
        with open(self._filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def search(self, keyword: str) -> list[dict[str, Any]]:
        """关键字匹配搜索(匹配 course、action、result、user_message 字段)。"""
        if not self._filepath.exists():
            return []
        results: list[dict[str, Any]] = []
        with open(self._filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # 在多个字段中搜索关键字
                searchable = " ".join([
                    str(record.get("action", "")),
                    str(record.get("course", "")),
                    str(record.get("result", "")),
                    str(record.get("user_message", "")),
                ])
                if keyword in searchable:
                    results.append(record)
        return results

    def get_recent(self, n: int = 10) -> list[dict[str, Any]]:
        """获取最近 N 条记录。"""
        if not self._filepath.exists():
            return []
        records: list[dict[str, Any]] = []
        with open(self._filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records[-n:]

    def cleanup_old(self) -> None:
        """删除 90 天之前的记录。"""
        if not self._filepath.exists():
            return
        cutoff = datetime.now() - timedelta(days=90)
        kept: list[dict[str, Any]] = []
        with open(self._filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    ts = datetime.fromisoformat(record["timestamp"])
                    if ts >= cutoff:
                        kept.append(record)
                except (KeyError, ValueError):
                    # 没有时间戳或格式错误, 保留
                    kept.append(record)
        with open(self._filepath, "w", encoding="utf-8") as f:
            for record in kept:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
