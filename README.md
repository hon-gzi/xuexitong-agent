# XuexitongAgent - 学习通智能助手

基于大语言模型的学习通自动化助手，支持自动答题、作业提交、视频播放等功能。

## ⚠️ 重要声明

**本项目仅供学习交流使用，请勿用于违反学校规定的行为。使用本工具产生的任何后果由用户自行承担。**

## ✨ 核心功能

- 🔐 **自动登录** - 支持账号密码登录和扫码登录
- 📝 **智能答题** - 基于 LLM 自动分析题目并作答
- 📹 **视频播放** - 自动播放课程视频
- 📊 **作业管理** - 自动获取并提交作业

## 🛡️ 安全提示

**本项目需要配置大模型 API Key 才能使用：**

1. 用户需要自己申请大模型的 API Key
2. API Key 仅存储在本地 `.env` 文件中
3. `.env` 文件已通过 `.gitignore` 保护，**绝不会上传到 GitHub**
4. 请勿在任何公开场合分享你的 API Key

## 📋 环境要求

- Python 3.9+
- Playwright（用于浏览器自动化）
- 大模型 API Key（支持 OpenAI、DeepSeek、Mimo 等）

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
pip install -r xuexitong-agent/requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 3️⃣ 配置 API Key

```bash
# 复制环境变量模板
cp xuexitong-agent/.env.example xuexitong-agent/.env

# 编辑 .env 文件，填入你的 API Key
# Windows: notepad xuexitong-agent/.env
# macOS/Linux: nano xuexitong-agent/.env
```

`.env` 文件配置示例：

```env
# 选择 LLM 提供商（支持: mimo, openai, deepseek 等）
LLM_PROVIDER=mimo

# 填写你的 API Key
MIMO_API_KEY=your-api-key-here

# OpenAI（如果使用 OpenAI）
# OPENAI_API_KEY=sk-your-api-key-here

# DeepSeek（如果使用 DeepSeek）
# DEEPSEEK_API_KEY=sk-your-api-key-here
```

### 4️⃣ 运行程序

```bash
cd xuexitong-agent
python main.py
```

程序启动后会：
1. 自动打开浏览器
2. 跳转到学习通登录页面
3. 等待你手动完成登录（扫码或密码）
4. 登录成功后自动启动助手

## 📁 项目结构

```
Agent/
├── xuexitong-agent/          # 主项目目录
│   ├── agent/                # Agent 核心逻辑
│   │   ├── chat.py          # 聊天功能
│   │   ├── loop.py          # 主循环
│   │   ├── tools.py         # 工具集
│   │   └── ui.py            # UI 界面
│   ├── auth/                 # 认证模块
│   │   └── login.py         # 登录逻辑
│   ├── browser/              # 浏览器控制
│   │   └── driver.py        # Playwright 驱动
│   ├── course/               # 课程相关
│   ├── homework/             # 作业处理
│   │   ├── fetch.py         # 获取作业
│   │   ├── ocr_recognizer.py # OCR 识别
│   │   └── submit.py        # 提交作业
│   ├── llm/                  # 大模型接口
│   │   └── client.py        # LLM 客户端
│   ├── main.py               # 入口文件
│   ├── requirements.txt      # 依赖列表
│   ├── .env.example          # 环境变量模板
│   └── .env                  # 环境变量（不提交）
├── .gitignore                # Git 忽略配置
└── README.md                 # 说明文档
```

## 🔑 获取 API Key

### 国内推荐（访问更快）

| 提供商 | 获取地址 | 备注 |
|--------|----------|------|
| DeepSeek | https://platform.deepseek.com/ | 推荐，性价比高 |
| 智谱 AI | https://open.bigmodel.cn/ | GLM-4 模型 |
| 月之暗面 | https://platform.moonshot.cn/ | Kimi 模型 |

### 国际选项

| 提供商 | 获取地址 | 备注 |
|--------|----------|------|
| OpenAI | https://platform.openai.com/ | GPT-4/3.5 |
| Anthropic | https://console.anthropic.com/ | Claude 系列 |

## ⚙️ 支持的 LLM 提供商

在 `.env` 文件中设置 `LLM_PROVIDER`：

- `mimo` - Mimo AI
- `openai` - OpenAI GPT 系列
- `deepseek` - DeepSeek
- 其他兼容 OpenAI API 的服务

## 🔧 常见问题

### Q: 运行时提示找不到模块？
A: 确保已激活虚拟环境并安装依赖：
```bash
pip install -r xuexitong-agent/requirements.txt
```

### Q: Playwright 浏览器启动失败？
A: 安装 Playwright 浏览器：
```bash
playwright install chromium
```

### Q: API Key 报错？
A: 检查 `.env` 文件是否正确配置：
- 确保文件路径正确：`xuexitong-agent/.env`
- 确保 Key 没有多余空格或引号
- 确保选择正确的 `LLM_PROVIDER`

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

---

**⚠️ 再次提醒：请勿将 `.env` 文件提交到 Git！**