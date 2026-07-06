"""AgentCore — 新版 Agent 核心编排类。

职责:
- 接收用户文本输入
- 注入语义/情景记忆到 system prompt
- 意图路由选择可用工具子集
- ReAct 循环调用 LLM + 工具执行
- 将执行结果写入情景记忆
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from agent.memory.manager import MemoryManager
from agent.tools import TOOL_DEFINITIONS
from agent.tools import EXECUTORS

if TYPE_CHECKING:
    from browser.session import BrowserSession
    from llm.client import LLMClient

# ---------------------------------------------------------------------------
# 基础 System Prompt
# ---------------------------------------------------------------------------

_BASE_SYSTEM_PROMPT = """你是学习通助手，一个能帮用户自动刷课和做作业的 AI Agent。

你拥有以下工具：
- list_courses：查看用户的课程列表
- screenshot_chapters：截图课程章节列表（含完成状态标记），返回截图文件路径
- watch_course：刷指定课程的视频（系统会自动检测并跳过已完成的章节）
- list_assignments：查看某课程的老师布置的日常作业列表
- do_homework：自动完成老师布置的日常作业（AI 答题 + 自动提交）
- do_chapter_exercises：自动完成课程每个章节后面的练习题（章节测验）

刷课的标准流程：
1. 调用 watch_course 即可，系统会自动检测哪些章节已完成并跳过
2. 如果只想刷特定章节，可以通过 chapters 参数指定章节序号（从0开始）

重要区分——两种作业：
1. "日常作业"/"老师布置的作业" → 用 do_homework
2. "章节作业"/"章节练习"/"章节测验"/"每章后面的练习" → 用 do_chapter_exercises

当用户只说"做作业"但没有明确是哪种时，你必须主动询问：
"你说的是老师布置的日常作业，还是每个章节后面的练习题？"

工作原则：
1. 先理解用户意图，再选择合适的工具
2. 如果用户没有指定具体课程，先用 list_courses 获取列表，再询问用户
3. 用户说"刷课并做作业"就依次调用 watch_course 和 do_homework
4. 工具返回结果后，用简洁的中文总结执行情况
5. 如果工具执行失败，分析原因并告诉用户

严格禁止：
- 绝对不要编造工具调用结果！你必须真正调用工具才能获得结果
- 当用户要求"刷课"、"看视频"、"完成课程"等操作时，你必须按刷课流程执行
- 当用户要求"做作业"时，你必须调用 do_homework 或 do_chapter_exercises 工具
- 如果你不调用工具就直接回复，用户会认为你在欺骗他们
"""

# 意图 → 工具子集的关键词路由表
_INTENT_ROUTES: dict[str, list[str]] = {
    "刷课": ["watch_course", "screenshot_chapters", "list_courses"],
    "视频": ["watch_course", "list_courses"],
    "看课": ["watch_course", "list_courses"],
    "作业": ["do_homework", "list_assignments", "do_chapter_exercises", "list_courses"],
    "做题": ["do_homework", "list_assignments", "do_chapter_exercises", "list_courses"],
    "章节练习": ["do_chapter_exercises", "screenshot_chapters", "list_courses"],
    "章节测验": ["do_chapter_exercises", "screenshot_chapters", "list_courses"],
    "章节作业": ["do_chapter_exercises", "list_courses"],
    "课程": ["list_courses"],
    "截图": ["screenshot_chapters"],
    "列表": ["list_courses", "list_assignments"],
}


class AgentCore:
    """Agent 核心编排类。

    组合浏览器会话、LLM 推理、工具执行与三层记忆系统，提供 ReAct 循环。
    """

    def __init__(
        self,
        browser_session: BrowserSession,
        memory_manager: MemoryManager,
        llm_client: LLMClient | None = None,
    ) -> None:
        """
        Args:
            browser_session: BrowserSession 实例，管理 Playwright 浏览器。
            memory_manager: MemoryManager 实例，管理三层记忆。
            llm_client: LLMClient 实例（可选，默认为全局单例）。
        """
        self.browser = browser_session
        self.memory = memory_manager

        if llm_client is not None:
            self.llm_client = llm_client
        else:
            from llm.client import llm
            self.llm_client = llm

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def handle_message(self, user_text: str) -> str:
        """处理用户消息并返回 Agent 回复。

        流程:
        1. 将用户消息写入短期记忆
        2. 构建增强版 system prompt（注入语义记忆 + 近期情景）
        3. 初始化消息历史（system + user）
        4. ReAct 循环（最多 10 轮工具调用）
        """
        # 1. 写入短期记忆
        self.memory.short_term.add_message("user", user_text)

        # 2. 构建增强 prompt
        system_prompt = self.memory.build_enhanced_prompt(_BASE_SYSTEM_PROMPT)

        # 3. 初始化消息列表
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

        # 4. ReAct 循环
        for _iteration in range(10):
            # 意图路由：选择可用工具子集
            available_tools = self._route_intent(user_text)

            # 调用 LLM
            resp = await self._call_llm(messages, available_tools)
            if resp is None:
                return "[错误] LLM 调用失败"

            msg = resp.choices[0].message

            # 没有工具调用 → LLM 直接回复文本
            if not msg.tool_calls:
                reply = msg.content or ""
                self.memory.short_term.add_message("assistant", reply)
                return reply

            # 有工具调用 → 追加 assistant 消息到历史
            messages.append(self._msg_to_dict(msg))

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                print(f"[AgentCore] 调用工具: {fn_name}({fn_args})", flush=True)

                # 通过 EXECUTORS 字典执行（自动注册）
                executor_fn = EXECUTORS.get(fn_name)
                if executor_fn:
                    try:
                        result = await executor_fn(
                            self.browser.driver,
                            self.browser.page,
                            fn_args,
                            self.memory,
                        )
                    except Exception as e:
                        result = f"工具执行错误: {e}"
                else:
                    result = f"未知工具: {fn_name}"

                print(f"[AgentCore] 工具结果: {result[:200]}", flush=True)

                # 记录到情景记忆
                self.memory.record_tool_execution(fn_name, "", result)

                # 追加工具结果到消息历史
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        return "操作已执行完成。"

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _route_intent(self, user_text: str) -> list[dict]:
        """根据用户意图关键词路由到工具子集。"""
        for keyword, tool_names in _INTENT_ROUTES.items():
            if keyword in user_text:
                return [
                    t for t in TOOL_DEFINITIONS
                    if t["function"]["name"] in tool_names
                ]
        return TOOL_DEFINITIONS  # 默认：所有工具

    async def _call_llm(
        self,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> object | None:
        """调用 LLM，带指数退避重试。"""
        for attempt in range(4):
            try:
                resp = self.llm_client.client.chat.completions.create(
                    model=self.llm_client.model,
                    messages=messages,
                    tools=tools if tools else None,
                    temperature=0.1,
                    timeout=120.0,
                )
                return resp
            except Exception as e:
                print(f"[AgentCore] LLM 调用失败: {type(e).__name__}: {e}")
                if attempt < 3:
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    return None
        return None

    @staticmethod
    def _msg_to_dict(msg: object) -> dict:
        """将 LLM 响应消息对象转为字典，便于追加到 messages 列表。"""
        d: dict = {}
        d["role"] = msg.role if hasattr(msg, "role") else "assistant"
        if hasattr(msg, "content") and msg.content:
            d["content"] = msg.content
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        return d
