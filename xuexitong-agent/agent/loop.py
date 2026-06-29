"""Agent 主循环：监听用户消息 → ReAct 推理 → 回传结果"""

import asyncio
from playwright.async_api import Page
from browser.driver import BrowserDriver
from llm.client import llm
from agent.ui import setup_auto_inject, inject_widget, send_to_widget, show_typing
from agent.chat import ReActAgent
from agent.tools import ToolExecutor


class AgentLoop:
    def __init__(self, driver: BrowserDriver, page: Page):
        self.driver = driver
        self.page = page
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False

    def _on_user_message(self, text: str):
        print(f"[Agent] 收到用户消息: {text[:80]}")
        self._queue.put_nowait(text)

    async def start(self):
        # 注册 JS→Python 通信桥（跨导航持久化）
        await self.page.expose_function("_agent_send", self._on_user_message)

        # 注册自动注入：每次页面加载自动注入悬浮窗
        await setup_auto_inject(self.page)

        # 首次手动注入
        await inject_widget(self.page)

        executor = ToolExecutor(self.driver, self.page)
        agent = ReActAgent(llm.client, llm.model, executor)

        self._running = True
        await send_to_widget(self.page, "助手已就绪，可以开始下达指令了！", "system")

        while self._running:
            try:
                user_text = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if not user_text or not user_text.strip():
                continue
            user_text = user_text.strip()
            print(f"[Agent] 处理消息: {user_text[:80]}")

            await show_typing(self.page)

            try:
                result = await agent.run(user_text)
                print(f"[Agent] 准备发送回复到widget, 长度: {len(result)}, URL: {self.page.url[:80]}")
                await send_to_widget(self.page, result, "bot")
                print(f"[Agent] 回复已发送到widget")
            except Exception as e:
                import traceback
                print(f"[Agent] 执行出错: {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
                try:
                    await send_to_widget(self.page, f"执行出错: {e}", "error")
                except Exception:
                    pass

    async def stop(self):
        self._running = False
