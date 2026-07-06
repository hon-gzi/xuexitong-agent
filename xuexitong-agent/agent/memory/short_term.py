"""短期记忆 - 维护对话上下文"""

import os
import time
from typing import Any


class ShortTermMemory:
    """维护最近 20 条消息作为对话上下文。

    当消息超过 30 条时,将最旧的 10 条压缩为摘要段落并前置,
    保留最新的 20 条完整消息。
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """追加一条消息。"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })

    def get_messages(self) -> list[dict[str, Any]]:
        """返回最近 20 条消息。"""
        return self.messages[-20:]

    def get_system_context(self) -> str:
        """将最近 20 条消息格式化为纯文本,供 system prompt 注入。"""
        recent = self.get_messages()
        if not recent:
            return ""
        parts: list[str] = []
        for msg in recent:
            parts.append(f"[{msg['role']}] {msg['content']}")
        return "\n".join(parts)

    def compress_recent(self) -> None:
        """消息超过 30 条时,压缩最旧 10 条为摘要段落并前置。

        策略:
        1. 如果消息 <= 30 条,不做任何操作。
        2. 如果消息 > 30 条,取最旧的 10 条生成一个 "Previous conversations summary" 段落。
        3. 保留摘要段落 + 最新 20 条消息,总计约 21 条。
        """
        if len(self.messages) <= 30:
            return

        oldest = self.messages[:10]
        remaining = self.messages[10:]  # 20+ 条

        # 将最旧的 10 条拼接为一段摘要
        summary_parts: list[str] = []
        for msg in oldest:
            summary_parts.append(f"[{msg['role']}] {msg['content']}")
        summary_text = "Previous conversations summary:\n" + "\n".join(summary_parts)

        # 将摘要作为第一条消息插入,剩余取最后 19 条(保持总量 ~20)
        self.messages = [{"role": "system", "content": summary_text}] + remaining[-19:]
