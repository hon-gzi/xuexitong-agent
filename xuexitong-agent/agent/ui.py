"""浏览器内悬浮聊天窗注入"""

import asyncio
from playwright.async_api import Page

WIDGET_CSS = """
#agent-island {
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 999999;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
#agent-bubble {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    cursor: pointer;
    box-shadow: 0 4px 15px rgba(102,126,234,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.2s, box-shadow 0.2s;
    color: white;
    font-size: 24px;
}
#agent-bubble:hover {
    transform: scale(1.1);
    box-shadow: 0 6px 20px rgba(102,126,234,0.6);
}
#agent-panel {
    display: none;
    width: 380px;
    height: 520px;
    background: white;
    border-radius: 16px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.15);
    position: absolute;
    bottom: 68px;
    right: 0;
    flex-direction: column;
    overflow: hidden;
}
#agent-panel.open { display: flex; }
#agent-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 14px 18px;
    font-size: 15px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
}
#agent-messages {
    flex: 1;
    overflow-y: auto;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.agent-msg {
    max-width: 85%;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 13px;
    line-height: 1.5;
    word-break: break-word;
}
.agent-msg.user {
    align-self: flex-end;
    background: #667eea;
    color: white;
    border-bottom-right-radius: 4px;
}
.agent-msg.bot {
    align-self: flex-start;
    background: #f0f2f5;
    color: #333;
    border-bottom-left-radius: 4px;
}
.agent-msg.system {
    align-self: center;
    background: #e8f5e9;
    color: #2e7d32;
    font-size: 12px;
    border-radius: 8px;
}
.agent-msg.error {
    align-self: center;
    background: #ffebee;
    color: #c62828;
    font-size: 12px;
    border-radius: 8px;
}
.agent-typing {
    align-self: flex-start;
    background: #f0f2f5;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 13px;
    color: #999;
}
#agent-input-area {
    padding: 10px 14px;
    border-top: 1px solid #eee;
    display: flex;
    gap: 8px;
}
#agent-input {
    flex: 1;
    border: 1px solid #ddd;
    border-radius: 20px;
    padding: 8px 14px;
    font-size: 13px;
    outline: none;
    resize: none;
    height: 36px;
    max-height: 80px;
    font-family: inherit;
}
#agent-input:focus { border-color: #667eea; }
#agent-send {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: #667eea;
    color: white;
    border: none;
    cursor: pointer;
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
}
#agent-send:hover { background: #5a6fd6; }
#agent-send:disabled { background: #ccc; cursor: default; }
"""

WIDGET_JS = """
(function() {
    if (document.getElementById('agent-island')) return;

    const STORAGE_KEY = 'agent_chat_history';

    function loadHistory() {
        try {
            const data = localStorage.getItem(STORAGE_KEY);
            console.log('[Agent Widget] loadHistory:', data ? data.substring(0, 200) : 'null');
            return data ? JSON.parse(data) : null;
        } catch(e) { console.log('[Agent Widget] loadHistory error:', e); return null; }
    }

    function saveHistory(msgs) {
        try {
            const trimmed = msgs.slice(-50);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
            console.log('[Agent Widget] saveHistory:', trimmed.length, 'msgs');
        } catch(e) { console.log('[Agent Widget] saveHistory error:', e); }
    }

    const WELCOME = '你好！我是学习通助手，可以帮你：<br>• 刷课：「帮我刷线性代数的视频」<br>• 做作业：「帮我做新发布的作业」<br>• 查看课程：「有哪些课程」';

    const root = document.createElement('div');
    root.id = 'agent-island';
    root.innerHTML = `
        <div id="agent-panel">
            <div id="agent-header">
                <span>🤖</span>
                <span>学习通助手</span>
            </div>
            <div id="agent-messages"></div>
            <div id="agent-input-area">
                <textarea id="agent-input" placeholder="输入指令..." rows="1"></textarea>
                <button id="agent-send">➤</button>
            </div>
        </div>
        <div id="agent-bubble">🤖</div>
    `;
    document.body.appendChild(root);

    const bubble = document.getElementById('agent-bubble');
    const panel = document.getElementById('agent-panel');
    const input = document.getElementById('agent-input');
    const sendBtn = document.getElementById('agent-send');
    const messages = document.getElementById('agent-messages');

    // 恢复历史记录
    var chatLog = loadHistory() || [];
    if (chatLog.length > 0) {
        chatLog.forEach(function(msg) {
            const div = document.createElement('div');
            div.className = 'agent-msg ' + msg.type;
            div.innerHTML = msg.text.replace(/\\n/g, '<br>');
            messages.appendChild(div);
        });
        messages.scrollTop = messages.scrollHeight;
    } else {
        const div = document.createElement('div');
        div.className = 'agent-msg bot';
        div.innerHTML = WELCOME;
        messages.appendChild(div);
    }

    bubble.addEventListener('click', () => {
        panel.classList.toggle('open');
        if (panel.classList.contains('open')) input.focus();
    });

    function autoResize() {
        input.style.height = '36px';
        input.style.height = Math.min(input.scrollHeight, 80) + 'px';
    }
    input.addEventListener('input', autoResize);

    // 持久化消息数组

    function addMessage(text, type) {
        console.log('[Agent Widget] addMessage:', type, text.substring(0, 60));
        const typing = messages.querySelector('.agent-typing');
        if (typing) typing.remove();

        const div = document.createElement('div');
        div.className = 'agent-msg ' + type;
        div.innerHTML = text.replace(/\\n/g, '<br>');
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;

        chatLog.push({text: text, type: type});
        saveHistory(chatLog);
        return div;
    }

    function showTyping() {
        const div = document.createElement('div');
        div.className = 'agent-typing';
        div.textContent = '思考中...';
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }

    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;
        addMessage(text, 'user');
        input.value = '';
        autoResize();
        sendBtn.disabled = true;
        showTyping();
        try {
            await window._agent_send(text);
        } catch(e) {
            addMessage('发送失败: ' + e.message, 'error');
        }
        sendBtn.disabled = false;
    }

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    window._agent_add_message = addMessage;
    window._agent_show_typing = showTyping;
})();
"""


async def setup_auto_inject(page: Page):
    """注册自动注入脚本，每次页面加载都会自动注入悬浮窗（跨导航持久化）"""
    css_escaped = WIDGET_CSS.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\$")
    js_escaped = WIDGET_JS.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\$")

    auto_inject_js = f"""
    (function() {{
        // 只在主frame执行，避免在iframe中重复注入
        if (window !== window.top) return;

        function inject() {{
            console.log('[Agent] auto-inject running, URL:', location.href.substring(0, 80));
            if (document.getElementById('agent-island')) return;
            if (!document.body) return;

            const style = document.createElement('style');
            style.id = 'agent-style';
            style.textContent = `{css_escaped}`;
            document.head.appendChild(style);

            const script = document.createElement('script');
            script.textContent = `{js_escaped}`;
            document.body.appendChild(script);
            script.remove();
        }}

        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', inject);
        }} else {{
            inject();
        }}
    }})();
    """

    await page.add_init_script(auto_inject_js)
    print("[Agent] 自动注入脚本已注册")


async def inject_widget(page: Page):
    """手动注入悬浮窗（首次启动用）"""
    try:
        await page.wait_for_load_state("domcontentloaded")
        for _ in range(10):
            has_body = await page.evaluate("!!document.body")
            if has_body:
                break
            await asyncio.sleep(0.5)

        await page.evaluate(f"""
            (() => {{
                if (document.getElementById('agent-style')) return;
                const style = document.createElement('style');
                style.id = 'agent-style';
                style.textContent = `{WIDGET_CSS}`;
                document.head.appendChild(style);
            }})()
        """)
        await page.evaluate(WIDGET_JS)

        # 如果 widget 已存在（auto-inject 先跑了），手动触发历史加载
        await page.evaluate("""
            (() => {
                var el = document.getElementById('agent-messages');
                if (!el || el.children.length > 1) return;
                // 只有欢迎语时才尝试加载历史
                try {
                    var data = localStorage.getItem('agent_chat_history');
                    if (!data) return;
                    var msgs = JSON.parse(data);
                    if (!msgs || msgs.length === 0) return;
                    el.innerHTML = '';
                    msgs.forEach(function(m) {
                        var div = document.createElement('div');
                        div.className = 'agent-msg ' + m.type;
                        div.innerHTML = m.text.replace(/\\n/g, '<br>');
                        el.appendChild(div);
                    });
                    el.scrollTop = el.scrollHeight;
                } catch(e) {}
            })()
        """)

        exists = await page.evaluate("!!document.getElementById('agent-island')")
        if exists:
            print("[Agent] 悬浮窗注入成功")
        else:
            print("[Agent] 警告：悬浮窗注入后未找到 DOM 元素")
    except Exception as e:
        print(f"[Agent] 悬浮窗注入失败: {e}")


async def send_to_widget(page: Page, text: str, msg_type: str = "bot"):
    """从 Python 发送消息到聊天窗显示，同时写入 localStorage 确保持久化"""
    escaped = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)

        # 优先通过 widget 的 addMessage（它维护 chatLog 数组，避免重复写入）
        widget_loaded = False
        for _ in range(10):
            try:
                if await page.evaluate("!!window._agent_add_message"):
                    await page.evaluate(f"window._agent_add_message(`{escaped}`, '{msg_type}')")
                    widget_loaded = True
                    print("[Agent] widget DOM 更新成功")
                    break
            except Exception as e:
                print(f"[Agent] widget DOM 更新失败: {e}")
                break
            await asyncio.sleep(0.3)

        # widget 未加载时（如页面跳转中），直接写 localStorage 保底
        if not widget_loaded:
            save_js = f"""
            (function() {{
                try {{
                    var key = 'agent_chat_history';
                    var data = localStorage.getItem(key);
                    var msgs = data ? JSON.parse(data) : [];
                    msgs.push({{text: `{escaped}`, type: '{msg_type}'}});
                    msgs = msgs.slice(-50);
                    localStorage.setItem(key, JSON.stringify(msgs));
                    console.log('[Agent] localStorage fallback save ok, total:', msgs.length);
                }} catch(e) {{
                    console.log('[Agent] localStorage fallback save error:', e);
                }}
            }})();
            """
            await page.evaluate(save_js)
            print("[Agent] localStorage fallback 写入完成")
    except Exception as e:
        print(f"[Agent] 发送消息到悬浮窗失败: {type(e).__name__}: {e}")


async def show_typing(page: Page):
    """在聊天窗显示"思考中..."指示器"""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        exists = await page.evaluate("!!window._agent_show_typing")
        if exists:
            await page.evaluate("window._agent_show_typing()")
    except Exception:
        pass
