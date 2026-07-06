"""XuexitongAgent - 学习通智能助手

启动 HTTP Server，通过 API 与 Agent 交互。

用法：
  python main.py              # 默认端口 8000
  PORT=9000 python main.py    # 自定义端口
"""

import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":
    from server import app
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    print(f"Starting Xuexitong Agent on port {port}...")
    print("API docs: http://localhost:{port}/docs")
    print("Chat:     POST http://localhost:{port}/chat")
    print('Body:     {{"message": "帮我刷软件工程导论"}}')
    print()
    uvicorn.run(app, host="0.0.0.0", port=port)
