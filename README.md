# XuexitongAgent - 学习通智能助手

基于大语言模型的垂直智能体，支持自动刷课、答题、作业提交等功能。

## ⚠️ 重要声明

**本项目仅供学习交流使用，请勿用于违反学校规定的行为。使用本工具产生的任何后果由用户自行承担。**

## ✨ 核心功能

- 🤖 **智能体架构** — 基于 LLM 的 ReAct 循环，自主推理并选择工具
- 📚 **自动刷课** — 自动播放课程视频，支持倍速和章节筛选
- 📝 **智能答题** — 基于 LLM 自动分析题目（单选/多选/判断/填空/简答/编程/论文）
- 📹 **视频播放** — 自动检测并完成课程视频、PDF、PPT 等内容
- 🧠 **记忆系统** — 三层记忆架构，跨会话记住课程进度和用户偏好

## 🛡️ 安全提示

**本项目需要配置大模型 API Key 才能使用：**

1. 用户需要自己申请大模型的 API Key
2. API Key 仅存储在本地 `.env` 文件中
3. `.env` 文件已通过 `.gitignore` 保护，**绝不会上传到 GitHub**
4. 请勿在任何公开场合分享你的 API Key

## 📋 环境要求

- Python 3.10+
- Playwright（用于浏览器自动化）
- 大模型 API Key（支持 Agnes AI、OpenAI、DeepSeek、Mimo 等）

## 🚀 快速开始

### 1️⃣ 克隆项目

```bash
git clone https://github.com/hon-gzi/xuexitong-agent.git
cd xuexitong-agent
```

### 2️⃣ 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 3️⃣ 配置 API Key

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 API Key
# Windows: notepad .env
# macOS/Linux: nano .env
```

`.env` 文件配置示例：

```env
# 选择 LLM 提供商（支持: agnes, mimo, modelscope, openai, deepseek 等）
LLM_PROVIDER=agnes

# 填写你的 API Key
AGNES_API_KEY=sk-your-api-key-here

# OpenAI（如果使用 OpenAI）
# OPENAI_API_KEY=sk-your-api-key-here

# DeepSeek（如果使用 DeepSeek）
# DEEPSEEK_API_KEY=sk-your-api-key-here
```

### 4️⃣ 启动 Agent

```bash
python main.py
```

程序启动后：
1. 自动打开无头浏览器
2. 尝试使用 Cookie 自动登录
3. 启动 HTTP API 服务

### 5️⃣ 与 Agent 交互

```bash
# 发送消息
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我刷软件工程导论"}'

# 查看 Agent 状态
curl http://localhost:8000/status

# 查看 API 文档（交互式）
open http://localhost:8000/docs
```

## 📁 项目结构

```
xuexitong-agent/
├── agent/                  # Agent 核心
│   ├── core.py            # AgentCore — 核心调度器
│   ├── chat.py            # 向后兼容层（已弃用）
│   ├── memory/            # 记忆系统
│   │   ├── manager.py     # MemoryManager — 统一入口
│   │   ├── short_term.py  # 短期记忆（对话上下文）
│   │   ├── episodic.py    # 情景记忆（历史事件）
│   │   └── semantic.py    # 语义记忆（结构化知识）
│   └── tools/             # 工具模块（自动注册）
│       ├── __init__.py    # 自动发现并注册所有工具
│       ├── list_courses.py
│       ├── watch_course.py
│       ├── do_homework.py
│       └── ...
├── browser/               # 浏览器控制
│   ├── driver.py          # Playwright 驱动
│   └── session.py         # 浏览器会话管理
├── homework/              # 作业处理
│   ├── fetch.py           # 获取作业
│   ├── ocr_recognizer.py  # OCR 识别
│   └── submit.py          # 提交答案
├── llm/                   # 大模型接口
│   └── client.py          # LLM 客户端（支持多平台）
├── video/                 # 视频播放
│   └── player.py          # 视频播放器
├── server.py              # HTTP Server (FastAPI)
├── main.py                # 入口文件
├── requirements.txt       # 依赖列表
├── .env.example           # 环境变量模板
└── .env                   # 环境变量（不提交）
```

## 🔑 获取 API Key

### 国内推荐（访问更快）

| 提供商 | 获取地址 | 备注 |
|--------|----------|------|
| Agnes AI | https://apihub.agnes-ai.com/ | agnes-2.0-flash 模型，推荐 |
| DeepSeek | https://platform.deepseek.com/ | 性价比高 |
| 智谱 AI | https://open.bigmodel.cn/ | GLM-4 模型 |
| 月之暗面 | https://platform.moonshot.cn/ | Kimi 模型 |

### 国际选项

| 提供商 | 获取地址 | 备注 |
|--------|----------|------|
| OpenAI | https://platform.openai.com/ | GPT-4/3.5 |
| Anthropic | https://console.anthropic.com/ | Claude 系列 |

## ⚙️ 支持的 LLM 提供商

在 `.env` 文件中设置 `LLM_PROVIDER`：

- `agnes` - Agnes AI (agnes-2.0-flash) ← 默认
- `mimo` - Mimo AI (mimo-v2.5)
- `modelscope` - ModelScope (deepseek-ai/DeepSeek-V4-Pro)
- `openai` - OpenAI GPT 系列
- `deepseek` - DeepSeek
- 其他兼容 OpenAI API 的服务

## 🧠 记忆系统

Agent 采用三层记忆架构：

1. **短期记忆** — 管理当前对话上下文，自动压缩旧对话
2. **情景记忆** — 记录每次工具执行的历史事件，支持关键词搜索
3. **语义记忆** — 持久化课程进度和用户偏好，跨会话保留

## 🔧 常见问题

### Q: 运行时提示找不到模块？
A: 确保已激活虚拟环境并安装依赖：
```bash
pip install -r requirements.txt
```

### Q: Playwright 浏览器启动失败？
A: 安装 Playwright 浏览器：
```bash
playwright install chromium
```

### Q: API Key 报错？
A: 检查 `.env` 文件是否正确配置：
- 确保文件路径正确
- 确保 Key 没有多余空格或引号
- 确保选择正确的 `LLM_PROVIDER`

### Q: 如何保存登录态？
A: 在浏览器中手动登录后，访问：
```bash
curl -X POST http://localhost:8000/auth/save-cookies
```

### Q: OCR 识别失败？
A: 本项目使用 RapidOCR，首次运行会自动下载模型文件。如需手动安装：
```bash
pip install rapidocr-onnxruntime
```

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

提交前请确保：
1. 不要提交 `.env` 文件
2. 不要提交个人账号密码
3. 不要提交 API Key

## 📄 许可证

MIT License

## 🙏 致谢

- [Playwright](https://playwright.dev/) - 浏览器自动化框架
- [RapidOCR](https://github.com/RapidAI/RapidOCR) - OCR 识别引擎
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
- [OpenAI Python](https://github.com/openai/openai-python) - LLM 客户端

---

**⚠️ 再次提醒：请勿将 `.env` 文件提交到 Git！**
