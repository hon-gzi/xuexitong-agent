"""记忆管理器 - 统一入口, 组合三种记忆类型"""

from pathlib import Path

from agent.memory.short_term import ShortTermMemory
from agent.memory.episodic import EpisodeStore
from agent.memory.semantic import SemanticStore


class MemoryManager:
    """组合短期记忆、情景记忆和语义记忆, 提供统一操作接口。"""

    def __init__(
        self,
        episodes_file: str = "data/memory/episodes.jsonl",
        semantic_file: str = "data/memory/semantic.json",
    ) -> None:
        self.short_term = ShortTermMemory()
        self.episodic = EpisodeStore(filepath=Path(episodes_file))
        self.semantic = SemanticStore(filepath=Path(semantic_file))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_tool_execution(
        self,
        tool_name: str,
        course: str,
        result: str,
    ) -> None:
        """记录一次工具执行: 写入情景记忆 + 更新语义记忆(课程进度)。"""
        # 写入情景记忆
        self.episodic.add_episode(
            action=tool_name,
            course=course,
            result=result,
            user_message="",  # 工具执行时通常没有直接的用户消息
        )

        # 从结果中提取课程进度信息(简单解析)
        # 例如 "进度: 3/10 个视频已完成" 或 "3道题已作答"
        progress = 0
        total = 0
        # 尝试从 result 中解析 "X/Y" 格式
        for part in result.split("/"):
            part = part.strip()
            # 提取数字
            digits = ""
            for ch in part:
                if ch.isdigit():
                    digits += ch
                elif digits:
                    break
            if digits:
                if progress == 0:
                    progress = int(digits)
                else:
                    total = int(digits)
                    break

        if total > 0:
            self.semantic.update_course(
                name=course,
                progress=progress,
                total=total,
                last_action=tool_name,
            )

    def build_enhanced_prompt(self, base_prompt: str) -> str:
        """在基础 prompt 中注入语义记忆上下文 + 近期情景摘要。"""
        enhancements: list[str] = []

        # 语义记忆上下文
        semantic_text = self.semantic.get_context_text()
        if semantic_text:
            enhancements.append(f"[语义记忆]\n{semantic_text}")

        # 近期情景摘要(最近 5 条)
        recent_episodes = self.episodic.get_recent(n=5)
        if recent_episodes:
            episode_lines: list[str] = []
            for ep in recent_episodes:
                episode_lines.append(
                    f"- {ep['timestamp']} | {ep['action']} | {ep['course']} | {ep['result']}"
                )
            enhancements.append(
                f"[近期情景]\n" + "\n".join(episode_lines)
            )

        if enhancements:
            return (
                base_prompt
                + "\n\n---\n\n"
                + "\n\n".join(enhancements)
            )
        return base_prompt

    def get_relevant_episodes(self, query: str) -> list[dict]:
        """在情景记忆中按关键字搜索相关记录。"""
        return self.episodic.search(query)
