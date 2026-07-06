"""语义记忆 - 结构化知识(课程进度、用户偏好等)"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


# 数据文件路径(相对于项目根目录)
_SEMANTIC_FILE = Path("data/memory/semantic.json")

# 默认初始结构
_DEFAULT_DATA: dict[str, Any] = {
    "courses": [],
    "preferences": {},
}


def _now_iso() -> str:
    """返回当前 ISO 时间字符串。"""
    return datetime.now().isoformat(timespec="seconds")


class SemanticStore:
    """持久化存储结构化知识。

    包括课程进度、用户偏好等, 支持序列化为 text 注入 system prompt。
    """

    def __init__(self, filepath: Path | None = None) -> None:
        self._filepath = filepath or _SEMANTIC_FILE
        self.data: dict[str, Any] = dict(_DEFAULT_DATA)
        # 初始化时加载已有数据
        self.load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """从文件加载数据。文件不存在或损坏时使用默认值。"""
        if not self._filepath.exists():
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except (json.JSONDecodeError, OSError):
            self.data = dict(_DEFAULT_DATA)

    def save(self) -> None:
        """保存数据到文件。"""
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def update_course(
        self,
        name: str,
        progress: int,
        total: int,
        last_action: str,
    ) -> None:
        """更新课程状态。如果课程不存在则新增。"""
        # 查找是否已存在
        for course in self.data.get("courses", []):
            if course.get("name") == name:
                course["progress"] = progress
                course["total"] = total
                course["last_action"] = last_action
                course["last_seen"] = _now_iso()
                self.save()
                return
        # 新增课程
        if "courses" not in self.data:
            self.data["courses"] = []
        self.data["courses"].append({
            "name": name,
            "progress": progress,
            "total": total,
            "last_action": last_action,
            "last_seen": _now_iso(),
        })
        self.save()

    def get_preferences(self) -> dict[str, Any]:
        """读取用户偏好设置。"""
        return self.data.get("preferences", {})

    def set_preference(self, key: str, value: Any) -> None:
        """设置用户偏好。"""
        if "preferences" not in self.data:
            self.data["preferences"] = {}
        self.data["preferences"][key] = value
        self.save()

    def get_context_text(self) -> str:
        """将所有知识序列化为纯文本, 供 system prompt 注入。"""
        parts: list[str] = []

        # 课程进度
        courses = self.data.get("courses", [])
        if courses:
            parts.append("课程进度:")
            for c in courses:
                progress = c.get("progress", 0)
                total = c.get("total", 0)
                last_action = c.get("last_action", "")
                last_seen = c.get("last_seen", "")
                parts.append(
                    f"  - {c.get('name', '未知')}: "
                    f"进度 {progress}/{total}, "
                    f"上次操作: {last_action}, "
                    f"最近活跃: {last_seen}"
                )

        # 用户偏好
        prefs = self.data.get("preferences", {})
        if prefs:
            parts.append("用户偏好:")
            for k, v in prefs.items():
                parts.append(f"  - {k}: {v}")

        return "\n".join(parts)
