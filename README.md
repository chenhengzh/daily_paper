# Daily Paper

每日 arXiv 论文智能筛选系统。自动抓取论文、用 LLM 评分过滤，通过网页和 Android App 浏览。

## 功能

- 每日定时抓取 arXiv 新论文，按研究兴趣过滤
- LLM 自动评分（相关性、质量、新颖性、影响力）并生成中文摘要
- 网页端：论文列表、收藏夹、管理后台
- Android App（Expo）：手机浏览、收藏同步

---

## 目录结构

```
daily_paper/
├── run_webapp.py          # 服务启动入口
├── start.sh               # 一键启动脚本
├── requirements.txt
├── .env                   # 环境变量（需自行创建，见下方）
├── src/                   # 抓取 & 评分核心逻辑
│   ├── scraper.py
│   ├── filter.py
│   └── remote_llm_api.py
├── webapp/                # FastAPI 后端
│   ├── main.py
│   ├── models.py
│   ├── database.py
│   ├── routers/
│   └── services/
├── static/                # CSS
├── android/               # React Native (Expo) App
└── logs/                  # 运行日志
```

---

## 快速开始

### 1. 安装依赖

```bash
conda create -n daily python=3.12
conda activate daily
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写必填项
```

**`.env` 完整说明：**

```bash
# ── LLM API（必填）──────────────────────────────────────
OPENAI_API_TYPE=openai               # openai（默认）或 azure
OPENAI_BASE_URL=https://api.openai.com/v1  # OpenAI-compatible 网关地址

# 单个 Key
OPENAI_API_KEY=sk-...

# 多个 Key（逗号分隔）；配置后 OPENAI_API_KEY 可省略
# 总并发 = LLM_MAX_CONCURRENCY × key 数量
# OPENAI_API_KEYS=sk-key1,sk-key2,sk-key3

# ── Azure 模式（OPENAI_API_TYPE=azure 时填写）───────────
# AZURE_ENDPOINT=https://your-resource.openai.azure.com
# AZURE_API_KEY=your-azure-key
# AZURE_API_VERSION=2024-03-01-preview

# ── 模型与限流──────────────────────────────────────────
LLM_MODEL_NAME=gpt-4o        # 模型名称
LLM_QPM=20                   # 单个 Key 每分钟请求上限（多 Key 时自动 × key 数量）
LLM_MAX_CONCURRENCY=16       # 单个 Key 最大并发数
# LLM_TIMEOUT_S=120          # 单次请求超时（秒）
# LLM_API_RETRIES=6          # 失败重试次数

# ── Session 加密────────────────────────────────────────
# SECRET_KEY=your-secret     # 固定后重启不需要重新登录；不填则每次随机生成
```

### 3. 启动服务

```bash
./start.sh
```

首次访问 `http://localhost:8000`，先创建管理员账号（见下方）。

---

## start.sh 命令参考

| 命令 | 说明 |
|------|------|
| `./start.sh` | 启动 Web 服务（生产模式） |
| `./start.sh --dev` | 启动 Web 服务（开发模式，文件变更自动重载） |
| `./start.sh --android` | 启动 Expo 开发服务器（App 调试，development 模式） |
| `./start.sh --android-prod` | 启动 Expo 开发服务器（App 调试，production 模式） |
| `./start.sh --all` | 同时启动 Web 服务和 Expo 开发服务器 |
| `./start.sh --stop` | 停止所有已启动的服务 |
| `./start.sh --status` | 查看服务运行状态 |
| `./start.sh --create-admin` | 创建管理员账号 |
| `./start.sh --help` | 显示帮助 |

> **注意**：`--dev` 模式下文件保存会触发服务重启，定时任务可能在重启期间漏触发，生产环境请使用默认模式。

---

## run_webapp.py 参数参考

直接调用时可指定以下参数：

```bash
python run_webapp.py [--host HOST] [--port PORT] [--reload]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `0.0.0.0` | 监听地址 |
| `--port` | `8000` | 监听端口 |
| `--reload` | 关闭 | 开发模式，文件变更自动重载 |

---

## 初始化管理员账号

首次部署时创建管理员：

```bash
./start.sh --create-admin
```

按提示输入用户名和密码（密码至少 6 位）。

---

## 配置研究兴趣

登录后进入「配置」页面，设置：

- **研究兴趣领域**：如 `Agent, LLM, RL`
- **高信号关键词**：如 `agent, tool use, reasoning`
- **定时任务时间**：默认每天 18:00（Asia/Shanghai）
- **LLM API Key**：非管理员用户需填写自己的 Key

---

## Android App

### 前置条件

- 安装 [Expo Go](https://expo.dev/go)（版本 55）
- 手机与电脑在同一 WiFi

### 启动调试服务器

```bash
./start.sh --android
```

扫描终端中的二维码，在 Expo Go 中打开。App 内 Setup 页面填写服务器地址：

```
http://<电脑IP>:8000
```

查看电脑 IP：

```bash
ipconfig getifaddr en0       # macOS
ip route get 1.1.1.1 | awk '{print $7; exit}'  # Linux
```

> **注意**：手机访问时请使用局域网 IP，不要用 `localhost`。

### 构建 APK

```bash
cd android
npm install -g eas-cli
eas build --platform android --profile preview
```

---

## 日志

| 日志文件 | 内容 |
|----------|------|
| `logs/app.log` | Web 服务日志 |
| `logs/expo.log` | Expo 开发服务器日志 |

```bash
tail -f logs/app.log
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy + APScheduler |
| 数据库 | SQLite |
| 前端 | Jinja2 + 原生 JS |
| Android | React Native (Expo SDK 55) |
| LLM | OpenAI-compatible API |
