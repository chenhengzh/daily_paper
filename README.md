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
├── .env                   # 环境变量（需自行创建）
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

### 1. 环境准备

```bash
# Python 3.10+
conda create -n daily python=3.12
conda activate daily
pip install -r requirements.txt
```

### 2. 配置环境变量

复制模板并填写：

```bash
cp .env.example .env
```

`.env` 内容说明：

```bash
# LLM API（必填）
OPENAI_API_TYPE=openai          # openai 或 azure
OPENAI_BASE_URL=https://...     # OpenAI-compatible 网关地址
OPENAI_API_KEY=sk-...           # API Key
AZURE_MODEL_NAME=gpt-4o         # 模型名称

# 可选：Azure 模式
# OPENAI_API_TYPE=azure
# AZURE_ENDPOINT=https://...
# AZURE_API_KEY=...
# AZURE_API_VERSION=2024-03-01-preview

# Session 加密密钥（不填则每次启动随机生成，重启后需重新登录）
SECRET_KEY=your-secret-key-here

# 限流（默认 QPM=30，并发=8）
AZURE_QPM=30
AZURE_MAX_CONCURRENCY=8
```

### 3. 启动服务

```bash
./start.sh
```

或手动启动：

```bash
python run_webapp.py --host 0.0.0.0 --port 8000
```

首次访问 `http://localhost:8000`，注册账号时需要邀请码——第一个账号通过管理员接口创建，见下方。

### 4. 创建第一个账号

首次部署需要通过命令行创建管理员账号：

```bash
./start.sh --create-admin
```

或直接运行：

```bash
python -c "
import sys; sys.path.insert(0, '.')
from webapp.database import init_db, get_db_sync
from webapp.models import User
from webapp.auth import hash_password
init_db()
db = get_db_sync()
u = User(username='admin', password_hash=hash_password('your_password'), is_admin=True, is_active=True)
db.add(u); db.commit()
print('管理员账号创建成功')
"
```

---

## 配置研究兴趣

登录后进入「配置」页面，设置：

- **研究兴趣领域**：如 `Agent, LLM, RL`
- **高信号关键词**：如 `agent, tool use, reasoning`
- **定时任务时间**：默认每天 09:30（Asia/Shanghai）

---

## Android App 调试

### 前置条件

- 安装 [Expo Go](https://expo.dev/go)（版本 55）
- 手机与电脑在同一 WiFi

### 启动开发服务器

```bash
./start.sh --android
```

扫描终端中的二维码，在 Expo Go 中打开。

App 内 Setup 页面填写服务器地址：`http://<电脑IP>:8000`

查看电脑 IP：
```bash
ipconfig getifaddr en0
```

### 构建 APK

```bash
cd android
npm install -g eas-cli
eas build --platform android --profile preview
```

---

## 服务管理

| 操作 | 命令 |
|------|------|
| 启动（生产） | `./start.sh` |
| 启动（开发，热重载） | `./start.sh --dev` |
| 启动 Android 调试 | `./start.sh --android` |
| 查看日志 | `tail -f logs/app.log` |
| 停止服务 | `./start.sh --stop` |

---

## 手动触发抓取

登录后在网页右上角点击「触发」按钮，或通过 API：

```bash
curl -X POST http://localhost:8000/papers/trigger \
  -H "Cookie: dp_session=<your_session>"
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
