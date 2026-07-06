"""Xuexitong Agent HTTP Server — FastAPI 入口。

启动方式：
  python server.py          # 默认端口 8000
  PORT=9000 python server.py  # 自定义端口
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from browser.session import BrowserSession
from agent.core import AgentCore
from agent.memory.manager import MemoryManager

# ── 全局实例 ──────────────────────────────────────────────────

_browser: Optional[BrowserSession] = None
_agent: Optional[AgentCore] = None


# ── 生命周期管理 ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Agent 启动 / 关闭生命周期。"""
    global _browser, _agent

    # 启动
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    _browser = BrowserSession(headless=headless)
    await _browser.start()

    # 尝试 cookie 登录
    logged_in = await _browser.ensure_logged_in()
    if not logged_in:
        print("[Server] Cookie 登录失败，请在浏览器中手动登录")
        print("[Server] 登录后运行 POST /auth/save-cookies 保存凭证")

    memory = MemoryManager()
    _agent = AgentCore(_browser, memory)

    print("[Server] Agent 已启动，监听 http://0.0.0.0:8000")
    yield
    # 关闭
    await _browser.stop()
    print("[Server] Agent 已关闭")


app = FastAPI(
    title="Xuexitong Agent",
    description="学习通智能助手 — 自动刷课答题 API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 请求 / 响应模型 ──────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    memory_updated: bool = True


class SaveCookiesRequest(BaseModel):
    """保存当前浏览器 Cookie（用于手动登录后持久化）。"""
    pass


# ── 路由 ─────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """发送消息给 Agent，获取回复。"""
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent 尚未启动")

    reply = await _agent.handle_message(request.message)
    return ChatResponse(reply=reply)


@app.get("/status")
async def status():
    """获取 Agent 状态和近期活动。"""
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent 尚未启动")

    mem = _agent.memory
    return {
        "status": "running",
        "semantic": mem.semantic.get_context_text(),
        "recent_episodes": mem.episodic.get_recent(5),
        "short_term_count": len(mem.short_term.get_messages()),
    }


@app.get("/memory/semantic")
async def get_semantic_memory():
    """查看当前语义记忆（课程进度、用户偏好）。"""
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent 尚未启动")
    return _agent.memory.semantic.data


@app.get("/memory/episodes")
async def get_episodic_memory(limit: int = 10):
    """查看最近的情景记忆记录。"""
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent 尚未启动")
    return _agent.memory.episodic.get_recent(limit)


@app.get("/memory/episodes/search")
async def search_episodes(keyword: str):
    """按关键词搜索情景记忆。"""
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent 尚未启动")
    return _agent.memory.episodic.search(keyword)


@app.post("/auth/save-cookies")
async def save_cookies():
    """保存当前浏览器 Cookie 到文件，用于下次自动登录。"""
    if not _browser:
        raise HTTPException(status_code=503, detail="Browser 尚未启动")
    await _browser.save_cookies()
    return {"status": "ok", "message": "Cookie 已保存"}


# ── 入口 ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
