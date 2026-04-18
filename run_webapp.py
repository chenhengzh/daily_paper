#!/usr/bin/env python3
"""
启动 Daily Paper Web 应用。

用法：
  python run_webapp.py [--host HOST] [--port PORT] [--reload]

环境变量（可选）：
  SECRET_KEY         Session 加密密钥（不设则每次启动随机生成）
  AZURE_API_KEY      LLM API Key（或 OPENAI_API_KEY）
  AZURE_ENDPOINT     LLM API Endpoint
  AZURE_MODEL_NAME   模型名称
"""
import os
import sys

# 确保项目根目录和 src/ 都在 Python 路径中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
for p in [PROJECT_ROOT, SRC_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import argparse
import uvicorn

# 自动加载项目根目录的 .env 文件
_env_file = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动 Daily Paper Web 应用")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8000, help="端口（默认 8000）")
    parser.add_argument("--reload", action="store_true", help="开发模式：文件变更时自动重载")
    args = parser.parse_args()

    print(f"启动 Daily Paper Web 应用：http://{args.host}:{args.port}")
    uvicorn.run(
        "webapp.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
