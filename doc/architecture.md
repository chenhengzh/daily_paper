# Daily Paper 系统架构文档

## 目录

1. [快速开始](#1-快速开始)
   - 1.1 [环境准备](#11-环境准备)
   - 1.2 [配置环境变量](#12-配置环境变量)
   - 1.3 [启动服务](#13-启动服务)
   - 1.4 [创建第一个账号](#14-创建第一个账号)
   - 1.5 [配置研究兴趣](#15-配置研究兴趣)
   - 1.6 [Android App 调试](#16-android-app-调试)
2. [系统概述](#2-系统概述)
3. [整体架构](#3-整体架构)
4. [目录结构](#4-目录结构)
5. [核心模块详解](#5-核心模块详解)
   - 5.1 [arXiv 抓取（scraper.py）](#51-arxiv-抓取scraperpy)
   - 5.2 [LLM 评分（filter.py）](#52-llm-评分filterpy)
   - 5.3 [LLM API 管理（remote_llm_api.py）](#53-llm-api-管理remote_llm_apipy)
6. [Web 后端](#6-web-后端)
   - 6.1 [数据模型](#61-数据模型)
   - 6.2 [API 路由](#62-api-路由)
   - 6.3 [Pipeline 服务](#63-pipeline-服务)
   - 6.4 [定时调度](#64-定时调度)
7. [前端页面](#7-前端页面)
8. [Android App](#8-android-app)
9. [用户权限体系](#9-用户权限体系)
10. [配置参考](#10-配置参考)
11. [数据流全链路](#11-数据流全链路)

---

## 1. 快速开始

### 1.1 环境准备

```bash
# Python 3.10+，推荐 3.12
conda create -n daily python=3.12
conda activate daily
pip install -r requirements.txt
```

### 1.2 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填写以下必填项：

```bash
# LLM API（必填）
OPENAI_API_TYPE=openai                    # "openai" 或 "azure"
OPENAI_BASE_URL=https://api.openai.com/v1 # OpenAI-compatible 网关地址
OPENAI_API_KEY=sk-...                     # API Key
OPENAI_MODEL_NAME=gpt-4o                  # 模型名称

# Session 加密密钥（不填则每次重启后需重新登录）
SECRET_KEY=your-secret-key-here

# 限流（默认值通常够用；旧名 AZURE_QPM / AZURE_MAX_CONCURRENCY 向后兼容）
LLM_QPM=30               # 每分钟最大请求数
LLM_MAX_CONCURRENCY=8    # 最大并发数（多 key 时总并发 = LLM_MAX_CONCURRENCY × key 数量）
```

如果使用 Azure OpenAI，改为：

```bash
OPENAI_API_TYPE=azure
AZURE_ENDPOINT=https://your-resource.openai.azure.com
AZURE_API_KEY=your-azure-key
AZURE_API_VERSION=2024-03-01-preview
LLM_MODEL_NAME=gpt-4o
```

### 1.3 启动服务

```bash
# 生产模式（推荐，不会因文件变更自动重启）
./start.sh

# 开发模式（文件变更自动热重载，不适合生产）
./start.sh --dev
```

服务启动后访问 `http://localhost:8000`。

常用管理命令：

```bash
./start.sh --stop      # 停止服务
./start.sh --status    # 查看运行状态
tail -f logs/app.log   # 查看实时日志
```

> **注意：** 务必使用 `./start.sh`（生产模式）而非 `./start.sh --dev`。开发模式下，每次在编辑器保存文件都会触发服务重启，可能导致定时任务（09:30）在重启窗口期内被错过。

### 1.4 创建第一个账号

首次部署需通过命令行创建管理员账号：

```bash
./start.sh --create-admin
```

按提示输入用户名和密码（密码至少 6 位）。管理员账号具备用户管理和邀请码生成权限。

后续用户注册需要邀请码。登录管理员账号后，进入「管理」页面生成邀请码，分发给需要注册的用户。

### 1.5 配置研究兴趣

登录后进入「配置」页面，建议按以下顺序设置：

1. **arXiv 分类**：选择关注的论文分类，如 `cs.AI, cs.LG, cs.CL`
2. **关键词**：用于 arXiv 查询过滤，如 `Agent, LLM, Reinforcement Learning`
3. **研究兴趣表**：填写具体研究方向的名称和描述，供 LLM 评分参考
   - 示例：名称 `Agent`，描述 `LLM-based agents and tool use, excluding domain-specific applications`
4. **高信号关键词**：命中后提升论文优先级，如 `agent, tool use, reasoning`
5. **去强调关键词**：命中后降低优先级，如 `medical, biomedical`
6. **重要作者**：命中后提升优先级
7. **定时触发时间**：默认每天 09:30（Asia/Shanghai），可按需调整

配置保存后，点击页面右上角「触发」按钮手动抓取当日论文，验证配置是否生效。

### 1.6 Android App 调试

**前置条件：** 手机安装 [Expo Go](https://expo.dev/go)（版本 55），手机与电脑在同一 WiFi。

```bash
# 启动 Expo 开发服务器
./start.sh --android

# 查看电脑局域网 IP
ipconfig getifaddr en0
```

扫描终端中的二维码，在 Expo Go 中打开。App 内 Setup 页面填写服务器地址：`http://<电脑IP>:8000`。

**构建生产 APK：**

```bash
cd android
npm install -g eas-cli
eas build --platform android --profile preview
```

构建前需将 `android/src/config.ts` 中的 `APP_MODE` 改为 `'production'`，或使用：

```bash
./start.sh --android-prod
```

---

## 2. 系统概述


Daily Paper 是一个面向 AI 研究者的每日 arXiv 论文智能筛选系统。系统每天自动抓取 arXiv 新论文，通过 LLM 对每篇论文进行多维度评分和中文摘要生成，并以网页和 Android App 两种方式提供阅读体验。

**核心特性：**

- 每日定时抓取（默认 09:30 CST），支持手动触发
- LLM 五维评分：相关性、质量、新颖性、影响力、综合优先级
- 基于研究兴趣的个性化过滤，支持关键词信号调权
- 中文摘要（tldr_zh / summary_zh）自动生成
- 多用户支持，每用户独立配置和评分结果
- 论文收藏夹 + 基于论文的 AI 对话（chat）

**技术栈：**

| 层 | 技术 |
|----|------|
| 后端 | Python 3.12, FastAPI, SQLAlchemy, APScheduler |
| 数据库 | SQLite |
| 前端 | Jinja2, 原生 JS |
| Android | React Native (Expo SDK 55), TypeScript |
| LLM | OpenAI-compatible API（支持 Azure） |

---

## 3. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     客户端层                              │
│   浏览器 (Jinja2 + JS)        Android App (Expo)        │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP :8000
┌──────────────────────▼──────────────────────────────────┐
│                   FastAPI Web 服务                        │
│  /auth  /papers  /config  /admin  /logs                  │
│                                                          │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │  Scheduler │  │   Pipeline   │  │  Session / Auth │  │
│  │ (每分钟检查) │  │ (抓取+评分)  │  │  (bcrypt+cookie)│  │
│  └─────┬──────┘  └──────┬───────┘  └─────────────────┘  │
└────────┼────────────────┼────────────────────────────────┘
         │                │
         ▼                ▼
┌────────────────┐  ┌─────────────────────────────────────┐
│   SQLite DB    │  │           src/ 核心逻辑              │
│  7 张表        │  │  scraper.py → filter.py              │
└────────────────┘  │  remote_llm_api.py                  │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │         外部服务                      │
                    │  arXiv API (HTTPS)                   │
                    │  OpenAI-compatible LLM API (HTTPS)   │
                    └─────────────────────────────────────┘
```

---

## 4. 目录结构

```
daily_paper/
├── run_webapp.py              # 服务启动入口（uvicorn）
├── start.sh                   # 一键启动脚本
├── requirements.txt           # Python 依赖
├── .env                       # 环境变量（需自行创建）
│
├── src/                       # 核心抓取与评分逻辑（独立于 Web 框架）
│   ├── scraper.py             # arXiv 抓取
│   ├── filter.py              # LLM 评分 & 后处理
│   └── remote_llm_api.py      # LLM API 客户端（限流、重试）
│
├── webapp/                    # FastAPI 应用
│   ├── main.py                # 应用入口、中间件、路由注册
│   ├── models.py              # SQLAlchemy ORM 模型
│   ├── database.py            # DB 初始化、Session 工厂
│   ├── auth.py                # 密码哈希、会话鉴权
│   ├── routers/
│   │   ├── auth.py            # 登录 / 注册 / 登出
│   │   ├── papers.py          # 论文列表、触发、收藏、chat
│   │   ├── config.py          # 用户配置 CRUD
│   │   ├── admin.py           # 用户管理、邀请码
│   │   └── logs.py            # 统计数据、任务历史
│   ├── services/
│   │   ├── pipeline.py        # 抓取 + 评分 orchestration
│   │   └── scheduler.py       # APScheduler 定时触发
│   └── templates/             # Jinja2 HTML 模板
│       ├── base.html
│       ├── index.html         # 主页（论文列表）
│       ├── config.html        # 用户配置页
│       ├── admin.html         # 管理后台
│       └── logs.html          # 统计页
│
├── static/                    # CSS 静态资源
├── android/                   # React Native (Expo) App
│   └── src/
│       ├── config.ts          # APP_MODE 切换
│       ├── screens/           # 各页面组件
│       ├── hooks/             # usePapers, useBookmarks 等
│       └── api/               # axios 请求封装
├── logs/                      # 运行日志（app.log, expo.log）
└── doc/                       # 文档目录
```

---

## 5. 核心模块详解

### 5.1 arXiv 抓取（scraper.py）

**入口函数：**

```python
fetch_daily_papers(specified_date, keywords, categories, max_results=800)
```

**日期窗口转换：**

arXiv 的 `submittedDate` 使用 UTC 时间。系统将本地日期（Asia/Shanghai）转换为 UTC 窗口：

```
本地 2026-04-21 00:00 CST → UTC 2026-04-20 16:00
本地 2026-04-22 00:00 CST → UTC 2026-04-21 16:00

查询参数：submittedDate:[202604201600 TO 202604211600]
```

**查询构建（三级 fallback）：**

```
第一级（完整查询）：
  (cat:cs.AI OR cat:cs.LG OR ...) AND
  (ti:Agent OR abs:Agent OR ...) AND
  submittedDate:[start TO end]

第二级（分类查询，如第一级失败）：
  对每个 category 单独查询后合并去重

第三级（仅分类+日期，如关键词返回 0 结果）：
  (cat:cs.AI OR cat:cs.LG OR ...) AND
  submittedDate:[start TO end]
```

**二次过滤：**

arXiv API 返回结果后，Python 代码还会对 `published_date` 做二次验证，确保论文确实属于目标日期，避免 API 边界误差。

**返回字段：**

| 字段 | 说明 |
|------|------|
| arxiv_id | 如 `2504.12345` |
| title | 论文标题 |
| summary | 英文摘要 |
| url / abs_url / pdf_url | 各类链接 |
| published_date / updated_date | 发布/更新时间 |
| categories | arXiv 分类列表 |
| authors | 作者列表 |

> **注意：** arXiv 周末不发布新论文，周五投稿通常在周一统一发布。

---

### 5.2 LLM 评分（filter.py）

**入口函数：**

```python
rate_papers(papers, interests)
```

**Prompt 结构：**

系统扮演"高级 AI 研究者助手"，对每篇论文执行四步判断：

1. **相关性门槛**：与研究兴趣不匹配 → 直接 keep=false
2. **质量门槛**：摘要空洞、纯工程实现、学位论文 → keep=false
3. **评分校准**：约 5% 论文 ≥8.0 分，约 10% ≥7.5 分（避免虚高）
4. **模糊情况**：倾向 keep=true + 低分，而非直接拒绝

**五维评分（1-10 分）：**

| 维度 | 含义 |
|------|------|
| relevance_score | 与研究兴趣的契合程度 |
| quality_score | 方法严谨性与证据充分度 |
| novelty_claim_score | 创新性主张 |
| impact_score | 对领域的潜在影响 |
| overall_priority_score | 综合阅读优先级 |

**后处理信号调权（_postprocess_one）：**

| 信号类型 | 每次触发调整 | 上限 |
|----------|------------|------|
| 高信号关键词（如 "Agent"） | +0.15 | +0.8 |
| 突破性声明（如 "state-of-the-art"） | +0.10 | +0.4 |
| 重要作者命中 | +0.35 | 无上限 |
| 证据关键词（如 "ablation", "theorem"） | +0.12 | +0.5 |
| 去强调关键词 | -0.12 | -0.6 |
| 概念堆砌（≥3 个概念词且无证据） | -0.6 | 一次性 |

**硬过滤规则：**

- 标题包含 "thesis" / "dissertation" / "technical report" → keep=false，分数上限 3.0
- 单作者 + 无信号 + 无证据词 + 分数 ≥7.5 → 降分 -0.4
- 相关性 ≤3.0 + 无高信号 + 无重要作者 → keep=false

**Tier 分级（mark_high_priority）：**

| Tier | overall_priority_score |
|------|----------------------|
| S | ≥8.0 |
| A | ≥7.0 |
| B | ≥6.0 |
| C | <6.0 |

**降级模式（无 API Key）：**

当没有配置 LLM API Key 时，`_heuristic_fallback()` 用简单关键词匹配打分：`relevance = 2 + 2 * keyword_hits`，不生成中文摘要。

---

### 5.3 LLM API 管理（remote_llm_api.py）

**两种 API 模式：**

| 模式 | 客户端 | 关键配置 |
|------|--------|---------|
| openai | AsyncOpenAI | OPENAI_BASE_URL, OPENAI_API_KEY |
| azure | AsyncAzureOpenAI | AZURE_ENDPOINT, AZURE_API_KEY, AZURE_API_VERSION |

**QPM 限流（AsyncQpmRateLimiter）：**

```
最小间隔 = 60.0 / QPM
例：QPM=30 → 每次调用间隔 ≥ 2 秒
```

使用单调时钟 + asyncio.Lock 保证并发安全。

**并发控制：**

`asyncio.Semaphore(MAX_CONCURRENCY)` 限制同时进行的 API 调用数量（默认 8）。

**重试策略：**

```
最大重试次数：6
退避策略：指数退避（1s → 2s → 4s → ... → 120s）+ 随机抖动 0~2s
触发限流错误时：强制等待 ≥15s
超时设置：SDK 层 120s + asyncio.wait_for 双重保障
```

**返回格式：**

```python
(response_text: str, {"input_tokens": int, "output_tokens": int})
```

---

## 6. Web 后端

### 6.1 数据模型

#### User（用户）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| username | str unique | 登录名 |
| email | str nullable | |
| hashed_password | str | bcrypt |
| is_active | bool | 是否可登录 |
| is_admin | bool | 管理员权限 |
| user_type | str | "internal" 或 "external" |
| created_at | datetime | |

#### UserConfig（用户配置）

| 字段 | 类型 | 默认值 |
|------|------|--------|
| keywords_json | text | `["Agent"]` |
| categories_json | text | `["cs.AI","cs.LG","cs.CL"]` |
| interest_table_json | text | `[{"name":"Agent","description":"..."}]` |
| high_signal_keywords_json | text | `["Agent"]` |
| deemphasized_keywords_json | text | `[]` |
| notable_authors_json | text | `[]` |
| llm_api_key | str nullable | 用户自定义 API Key |
| llm_endpoint | str nullable | 用户自定义 endpoint |
| llm_model | str nullable | 用户自定义模型名 |
| max_results | int | 800 |
| high_priority_target | int | 15（每日精选目标数量）|
| auto_trigger | bool | true |
| trigger_hour / trigger_minute | int | 9 / 30 |

#### Paper（论文，全局共享）

所有用户共享同一份论文表，避免重复抓取。

| 字段 | 说明 |
|------|------|
| arxiv_id | 唯一标识，如 `2504.12345` |
| title / summary | 标题 / 英文摘要 |
| paper_date | 论文日期（用于按日期查询） |
| authors_json / categories_json | JSON 数组 |

#### DailyJob（每日任务）

每个用户每天一条记录，记录任务状态和 token 消耗。

| 字段 | 说明 |
|------|------|
| status | pending / scraping / rating / done / failed |
| scrape_count | 抓取到的论文数 |
| rated_count / kept_count | 评分数 / 保留数 |
| high_priority_count | 精选数量 |
| input_tokens / output_tokens | LLM token 消耗 |
| daily_summary_zh | AI 生成的每日摘要 |
| daily_ideas_zh | AI 生成的研究想法 |

#### UserPaperResult（用户论文评分结果）

每用户每篇论文一条记录，存储完整评分信息。

| 字段 | 说明 |
|------|------|
| keep | 是否保留展示 |
| interest_field / interest_subfield | 匹配的研究领域 |
| tldr / tldr_zh | 英文/中文简短摘要 |
| summary_zh | 详细中文摘要 |
| relevance/quality/novelty/impact/overall_priority_score | 五维分数 |
| tier | S/A/B/C |
| high_priority / high_priority_rank | 是否精选及排名 |
| signal_*_json | 触发的信号关键词（用于 UI 展示） |
| is_bookmarked | 是否收藏 |

#### InviteCode（邀请码）

一次性使用，注册后自动删除。

#### ChatMessage（论文对话）

按 (user_id, paper_id) 存储对话历史，role 为 "user" 或 "assistant"。

---

### 6.2 API 路由

#### /auth

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /auth/login | 登录页面 |
| POST | /auth/login | 验证账号密码，写入 session cookie |
| GET | /auth/register | 注册页面 |
| POST | /auth/register | 验证邀请码，创建用户和默认配置 |
| POST | /auth/logout | 清除 session |

#### /papers

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /papers/ | 主页（HTML） |
| GET | /papers/api | 获取指定日期的论文列表和任务状态（JSON） |
| GET | /papers/dates | 获取用户有数据的日期列表 |
| GET | /papers/summary | 获取每日 AI 摘要和研究想法 |
| POST | /papers/{arxiv_id}/bookmark | 收藏论文 |
| DELETE | /papers/{arxiv_id}/bookmark | 取消收藏 |
| GET | /papers/bookmarks | 收藏的 arxiv_id 列表 |
| GET | /papers/bookmarks/full | 收藏的完整论文信息 |
| GET | /papers/{arxiv_id} | 单篇论文详情 |
| GET | /papers/{arxiv_id}/chat/history | 论文对话历史 |
| POST | /papers/{arxiv_id}/chat | 发送消息（SSE 流式返回） |
| POST | /papers/trigger | 手动触发 pipeline（后台执行） |
| GET | /papers/trigger/status | 查询触发状态 |
| GET | /papers/trigger/progress | 触发进度（SSE 流式） |

#### /config

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /config/ | 配置页面（HTML） |
| GET | /config/api | 获取当前配置 |
| PUT | /config/api | 更新配置（关键词、分类、LLM 凭证等） |
| GET | /config/defaults | 获取默认配置模板 |

#### /admin

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /admin/ | 管理后台（HTML，需 is_admin） |
| GET | /admin/users | 用户列表 |
| PUT | /admin/users/{user_id} | 修改用户状态/类型/权限 |
| GET | /admin/invite-codes | 邀请码列表 |
| POST | /admin/invite-codes | 批量生成邀请码 |
| DELETE | /admin/invite-codes/{code} | 删除邀请码 |

#### /logs

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /logs/ | 统计页面（HTML，需 is_admin） |
| GET | /logs/api/stats | 各用户 token 消耗统计（最近 N 天） |
| GET | /logs/api/jobs | 任务历史列表 |

---

### 6.3 Pipeline 服务

**pipeline.py** 是抓取和评分的核心编排层。

**scrape_and_store(target_date, ...)：**

1. 调用 `src/scraper.py` 抓取论文
2. 将论文 upsert 到 Paper 表（以 arxiv_id 去重）
3. 返回原始论文列表

**rate_papers_for_user(user_id, target_date, force=False)：**

```
1. 加载用户配置
2. 创建/获取 DailyJob 记录
3. 从 Paper 表获取目标日期所有论文
4. 注入用户个性化配置到 filter 模块：
   - NOTABLE_AUTHORS
   - HIGH_SIGNAL_KEYWORDS
   - DEEMPHASIZED_KEYWORDS
5. 注入 LLM 凭证（internal 用户用系统 Key，external 用户用自己的 Key）
6. 并发调用 _rate_one_paper() 评分
7. 累计 token 消耗
8. 后处理（_postprocess_one）
9. 结果 upsert 到 UserPaperResult
10. 标记精选（mark_high_priority）
11. 更新 DailyJob 状态为 done
12. 恢复原始环境变量和 filter 模块配置
```

> **重要设计**：Pipeline 通过模块级变量注入实现用户个性化，asyncio 单线程保证安全（不会并发污染）。

**手动触发（/papers/trigger）：**

- 触发后台线程，对最近 5 天逐日执行 scrape_and_store + rate_papers_for_user
- 通过 SSE（Server-Sent Events）实时推送进度到前端
- 跳过 admin 用户，避免消耗系统 API 配额

---

### 6.4 定时调度

**scheduler.py** 使用 APScheduler 的 AsyncIOScheduler，每分钟执行一次 `_check_and_trigger()`。

**触发逻辑：**

```python
for user in active_users:
    if auto_trigger and now.hour == trigger_hour and now.minute == trigger_minute:
        scrape_and_store(today)
        scrape_and_store(yesterday)
        rate_papers_for_user(user.id, today)
        rate_papers_for_user(user.id, yesterday)
```

**已知限制：**

- 每分钟只检查一次，若服务在 9:30 那一分钟内重启（如开发模式 `--reload` 热重载），则该次触发会被错过
- 不支持补跑（错过后不会自动重试，需手动触发）

**建议：** 生产环境使用 `./start.sh`（无 `--reload`），避免文件变更触发重启。

---

## 7. 前端页面

### index.html（主页）

主要功能：

- 日期选择器：切换不同日期的论文列表
- 视图切换：精选（keep=true + high_priority）/ 全部（keep=true）/ 收藏夹
- 领域筛选：按 interest_field 过滤
- 全文搜索：标题 + 摘要本地搜索
- 论文卡片：展示标题、作者、分数、Tier、中文摘要、信号关键词
- 触发按钮：手动触发 pipeline，实时显示进度
- 每日摘要：展示 AI 生成的当日研究概述和研究想法
- 论文详情侧栏：点击论文展开详情，支持 AI 对话

### config.html（配置页）

支持配置：

- 关键词列表（用于 arXiv 查询过滤）
- arXiv 分类（cs.AI / cs.LG / cs.CL 等）
- 研究兴趣表（名称 + 描述，供 LLM 评分参考）
- 高信号关键词（提分）/ 去强调关键词（降分）
- 重要作者列表（提分）
- 自定义 LLM API Key / Endpoint / 模型名
- 最大抓取数量 / 精选目标数量
- 定时触发开关和时间设置

### admin.html（管理后台）

- 用户列表：查看所有用户，修改 user_type / is_active / is_admin
- 邀请码管理：批量生成（可指定 internal/external 类型），删除

### logs.html（统计页）

- 各用户最近 30 天的 token 消耗汇总
- 每日任务成功/失败统计
- 任务历史列表（状态、论文数、耗时）

---

## 8. Android App

### 技术栈

- React Native (Expo SDK 55)
- TypeScript
- React Query（数据请求）
- axios（HTTP 客户端，30s 超时）

### 运行模式（android/src/config.ts）

```typescript
export const APP_MODE: 'production' | 'development' = 'development';
export const PRODUCTION_SERVER_URL = 'http://39.106.96.191';
```

- **development**：显示 Setup 页面，手动填写服务器地址
- **production**：直接连接硬编码的生产服务器地址

切换模式：`./start.sh --android`（development）或 `./start.sh --android-prod`（production）

### 主要页面

| 页面 | 功能 |
|------|------|
| LoginScreen | 账号密码登录 |
| SetupScreen | 填写服务器地址（development 模式） |
| PaperListScreen | 论文列表，日期选择，搜索，触发 pipeline |
| PaperDetailScreen | 论文详情，中文摘要，AI 对话 |
| BookmarksScreen | 收藏夹，按分数排序 |
| SettingsScreen | 修改用户配置 |

### 关键 Hook

**usePapers.ts：**

```typescript
// 返回值
{
  dates,           // 有数据的日期列表
  selectedDate,    // 当前选中日期
  filteredPapers,  // 过滤后的论文列表
  fields,          // 所有 interest_field
  activeField,     // 当前筛选的领域
  viewMode,        // "selected" | "all"
  job,             // 当前日期的 DailyJob 状态
  searchQuery,
  loading, error,
  refresh,
}
```

**触发逻辑（api/trigger.ts）：**

1. POST /papers/trigger
2. 每 5 秒轮询 GET /papers/trigger/status
3. 状态变为 done/failed 后停止轮询

---

## 9. 用户权限体系

### 角色层级

| 角色 | 条件 | 权限 |
|------|------|------|
| 普通用户 | is_admin=false | 查看自己的论文、配置、收藏、chat |
| 管理员 | is_admin=true | 额外：用户管理、邀请码、统计页 |
| 超级管理员 | username="admin" | 额外：可修改其他用户的 is_admin 标志 |

### 用户类型

| 类型 | LLM API Key 来源 |
|------|----------------|
| internal | 使用系统环境变量（OPENAI_API_KEY 等） |
| external | 必须在配置页填写自己的 API Key |

### 邀请码

- 注册时必须填写有效邀请码
- 邀请码分为 internal / external 两种，决定注册用户的 user_type
- 使用后立即删除（一次性）

---

## 10. 配置参考

### 环境变量（.env）

```bash
# LLM API（必填）
OPENAI_API_TYPE=openai          # "openai" 或 "azure"
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-...
OPENAI_MODEL_NAME=gpt-4o        # 或其他兼容模型

# Azure 模式（可选）
# OPENAI_API_TYPE=azure
# AZURE_ENDPOINT=https://your-resource.openai.azure.com
# AZURE_API_KEY=...
# AZURE_API_VERSION=2024-03-01-preview

# Session 加密（不填则每次启动随机生成）
SECRET_KEY=your-secret-key

# 限流（旧名 AZURE_QPM / AZURE_MAX_CONCURRENCY 向后兼容）
LLM_QPM=30                      # 每分钟请求数
LLM_MAX_CONCURRENCY=8           # 最大并发数
```

### start.sh 选项

| 命令 | 说明 |
|------|------|
| `./start.sh` | 生产模式启动 Web 服务 |
| `./start.sh --dev` | 开发模式（热重载，**不适合生产**） |
| `./start.sh --android` | 启动 Expo 开发服务器（development 模式） |
| `./start.sh --android-prod` | 启动 Expo 开发服务器（production 模式） |
| `./start.sh --all` | 同时启动 Web 和 Expo |
| `./start.sh --stop` | 停止所有服务 |
| `./start.sh --status` | 查看服务状态 |
| `./start.sh --create-admin` | 创建管理员账号 |

---

## 11. 数据流全链路

### 定时触发完整流程

```
09:30 CST
  │
  ▼
scheduler._check_and_trigger()
  │ 检查每个用户的 trigger_hour:trigger_minute
  │
  ▼
pipeline.scrape_and_store(today)
pipeline.scrape_and_store(yesterday)
  │ 调用 src/scraper.fetch_daily_papers()
  │ → arXiv API 查询（3级 fallback）
  │ → 二次日期过滤
  │ → upsert 到 Paper 表
  │
  ▼
pipeline.rate_papers_for_user(user_id, date)
  │ 加载用户配置
  │ 注入个性化参数到 filter 模块
  │ 注入 LLM 凭证
  │
  ▼
src/filter._rate_one_paper() × N（并发）
  │ 构建 prompt（interests + title + abstract）
  │ → remote_llm_api.chat_completion_text()
  │   → QPM 限流等待
  │   → 获取 semaphore
  │   → LLM API 调用（最多重试 6 次）
  │   → 返回 JSON 评分结果
  │ 解析 JSON，后处理调权
  │
  ▼
upsert UserPaperResult（评分 + 中文摘要）
mark_high_priority（设置 tier + rank）
更新 DailyJob.status = "done"
恢复环境变量和 filter 模块配置
```

### 手动触发流程

```
用户点击"触发"按钮
  │
  ▼
POST /papers/trigger
  │ 启动后台线程
  │ 对最近 5 天逐日执行 scrape_and_store + rate_papers_for_user
  │
  ├── GET /papers/trigger/progress（SSE）
  │     实时推送进度事件到前端
  │
  └── GET /papers/trigger/status
        轮询是否完成（Android App 使用）
```

### 论文展示流程

```
用户打开页面 / 切换日期
  │
  ▼
GET /papers/api?date=2026-04-21
  │ 查询 UserPaperResult JOIN Paper
  │ 按 overall_priority_score DESC 排序
  │ 返回完整评分字段
  │
  ▼
前端本地筛选（精选/全部/收藏夹，领域，搜索词）
  │
  ▼
渲染论文卡片（Tier 徽章，分数，中文摘要，信号词）
```
