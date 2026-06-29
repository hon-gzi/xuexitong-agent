"""ReAct Agent：LLM 通过 function calling 自主选择工具，观察结果，循环推理"""

import json
from openai import OpenAI
from agent.tools import TOOL_DEFINITIONS, ToolExecutor

SYSTEM_PROMPT = """你是学习通助手，一个能帮用户自动刷课和做作业的 AI Agent。

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


class ReActAgent:
    def __init__(self, llm_client: OpenAI, model: str, executor: ToolExecutor):
        self.client = llm_client
        self.model = model
        self.executor = executor
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    async def run(self, user_message: str) -> str:
        """执行一轮 ReAct 循环，返回最终回复"""
        self.messages.append({"role": "user", "content": user_message})

        for _ in range(10):  # 最多 10 轮工具调用
            resp = None
            for attempt in range(4):
                try:
                    print(f"[Agent] 调用 LLM (尝试 {attempt+1}/4)...", flush=True)
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        tools=TOOL_DEFINITIONS,
                        temperature=0.1,
                        timeout=120.0,
                    )
                    print(f"[Agent] LLM 响应: choices={len(resp.choices) if resp.choices else 0}", flush=True)
                    break
                except Exception as e:
                    print(f"[Agent] LLM 调用失败: {type(e).__name__}: {e}", flush=True)
                    if attempt < 3:
                        print(f"[Agent] {2*(attempt+1)}秒后重试...", flush=True)
                        import time
                        time.sleep(2 * (attempt + 1))
                    else:
                        raise

            # 检查响应是否有效
            if not resp or not resp.choices or len(resp.choices) == 0:
                print(f"[Agent] LLM 返回空响应: {resp}", flush=True)
                raise ValueError("LLM 返回空响应，无 choices")

            msg = resp.choices[0].message
            self.messages.append(msg)

            # 没有工具调用，LLM 直接回复文本
            if not msg.tool_calls:
                reply = msg.content or ""
                # 检测：用户要求操作但LLM没调用工具就回复了，强制重试
                action_keywords = ["刷课", "视频", "作业", "练习", "看课", "完成", "自动"]
                prev_msg = self.messages[-2] if len(self.messages) >= 2 else None
                user_msg = prev_msg.content if prev_msg and hasattr(prev_msg, "content") else ""
                if any(kw in user_msg for kw in action_keywords) and not any(
                    (m.get("tool_calls") if isinstance(m, dict) else getattr(m, "tool_calls", None))
                    for m in self.messages
                    if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) == "assistant"
                ):
                    print("[Agent] LLM未调用工具，强制重试...")
                    self.messages.append({
                        "role": "user",
                        "content": "你还没有调用工具！请调用正确的工具来执行用户请求，不要直接回复结果。",
                    })
                    continue
                print(f"[Agent] LLM 回复: {reply[:100]}")
                return reply

            # 执行所有工具调用
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                print(f"[Agent] 调用工具: {fn_name}({fn_args})")
                result = await self.executor.execute(fn_name, fn_args)
                print(f"[Agent] 工具结果: {result[:100]}")

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        return "操作已执行完成。"
