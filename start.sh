#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

WEBAPP_PID_FILE="$SCRIPT_DIR/.webapp.pid"
EXPO_PID_FILE="$SCRIPT_DIR/.expo.pid"

usage() {
  echo "用法: ./start.sh [选项]"
  echo ""
  echo "选项:"
  echo "  (无参数)           启动 Web 服务（生产模式）"
  echo "  --dev              启动 Web 服务（开发模式，文件变更自动重载）"
  echo "  --android          启动 Expo 开发服务器（App 调试，development 模式）"
  echo "  --android-prod     启动 Expo 开发服务器（App 调试，production 模式）"
  echo "  --all              同时启动 Web 服务和 Expo 开发服务器"
  echo "  --stop             停止所有已启动的服务"
  echo "  --create-admin     创建管理员账号"
  echo "  --status           查看服务运行状态"
  echo "  -h, --help         显示帮助"
  exit 0
}

log() { echo "[$(date '+%H:%M:%S')] $*"; }

check_env() {
  if [ ! -f "$SCRIPT_DIR/.env" ]; then
    log "警告：未找到 .env 文件，请复制 .env.example 并填写配置"
    log "  cp .env.example .env"
  fi
}

get_lan_ip() {
  # macOS
  ipconfig getifaddr en0 2>/dev/null || \
  ipconfig getifaddr en1 2>/dev/null || \
  # Linux: 取第一个非 127 的 IP
  ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || \
  hostname -I 2>/dev/null | awk '{print $1}' || \
  echo "127.0.0.1"
}

start_webapp() {
  local reload_flag=""
  [ "$1" = "--dev" ] && reload_flag="--reload"

  if [ -f "$WEBAPP_PID_FILE" ]; then
    local pid
    pid=$(cat "$WEBAPP_PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      log "Web 服务已在运行（PID $pid）"
      return
    fi
  fi

  check_env
  log "启动 Web 服务..."
  python run_webapp.py --host 0.0.0.0 --port 8000 $reload_flag >> logs/app.log 2>&1 &
  echo $! > "$WEBAPP_PID_FILE"
  sleep 2

  local pid
  pid=$(cat "$WEBAPP_PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    local lan_ip
    lan_ip=$(get_lan_ip)
    log "Web 服务已启动（PID $pid）"
    log "  本机访问: http://localhost:8000"
    log "  局域网:   http://$lan_ip:8000"
    log "  日志:     tail -f logs/app.log"
  else
    log "错误：Web 服务启动失败，请查看 logs/app.log"
    rm -f "$WEBAPP_PID_FILE"
    exit 1
  fi
}

set_app_mode() {
  local mode="$1"  # 'development' or 'production'
  local config="$SCRIPT_DIR/android/src/config.ts"
  sed -i.bak "s/APP_MODE: 'production' | 'development' = '[^']*'/APP_MODE: 'production' | 'development' = '$mode'/" "$config" && rm -f "$config.bak"
  log "App 模式已切换为: $mode"
}

start_expo() {
  local mode="${1:-development}"
  if [ -f "$EXPO_PID_FILE" ]; then
    local pid
    pid=$(cat "$EXPO_PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      log "Expo 服务已在运行（PID $pid）"
      return
    fi
  fi

  if [ ! -d "$SCRIPT_DIR/android/node_modules" ]; then
    log "安装 Android 依赖..."
    cd "$SCRIPT_DIR/android" && npm install
    cd "$SCRIPT_DIR"
  fi

  set_app_mode "$mode"

  local lan_ip
  lan_ip=$(get_lan_ip)

  log "启动 Expo 开发服务器（LAN IP: $lan_ip，模式: $mode）..."
  cd "$SCRIPT_DIR/android" && \
    REACT_NATIVE_PACKAGER_HOSTNAME="$lan_ip" \
    EXPO_NO_DOTENV=1 \
    ./node_modules/.bin/expo start --lan --port 8081 \
    >> "$SCRIPT_DIR/logs/expo.log" 2>&1 &
  echo $! > "$EXPO_PID_FILE"
  sleep 8

  local pid
  pid=$(cat "$EXPO_PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    log "Expo 服务已启动（PID $pid）"
    log "  在 Expo Go 中扫码或输入: exp://$lan_ip:8081"
    log "  App 服务器地址填写:      http://$lan_ip:8000"
    log "  日志: tail -f logs/expo.log"
    echo ""
    # 打印二维码
    python3 -c "
import qrcode
url = 'exp://$lan_ip:8081'
qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=2)
qr.add_data(url)
qr.make(fit=True)
qr.print_ascii(invert=True)
print(f'URL: {url}')
" 2>/dev/null || log "（安装 qrcode 包可显示二维码：pip install qrcode）"
  else
    log "错误：Expo 服务启动失败，请查看 logs/expo.log"
    rm -f "$EXPO_PID_FILE"
    exit 1
  fi
}

stop_services() {
  local stopped=0
  for pidfile in "$WEBAPP_PID_FILE" "$EXPO_PID_FILE"; do
    if [ -f "$pidfile" ]; then
      local pid
      pid=$(cat "$pidfile")
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        log "已停止进程 PID $pid"
        stopped=$((stopped + 1))
      fi
      rm -f "$pidfile"
    fi
  done
  # 也尝试清理残留的 expo 子进程
  pkill -f "expo start" 2>/dev/null || true
  [ $stopped -eq 0 ] && log "没有正在运行的服务"
}

show_status() {
  echo "=== Daily Paper 服务状态 ==="
  if [ -f "$WEBAPP_PID_FILE" ]; then
    local pid
    pid=$(cat "$WEBAPP_PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Web 服务:  运行中（PID $pid）"
    else
      echo "Web 服务:  已停止（PID 文件残留）"
    fi
  else
    echo "Web 服务:  未启动"
  fi

  if [ -f "$EXPO_PID_FILE" ]; then
    local pid
    pid=$(cat "$EXPO_PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Expo 服务: 运行中（PID $pid）"
    else
      echo "Expo 服务: 已停止（PID 文件残留）"
    fi
  else
    echo "Expo 服务: 未启动"
  fi
}

create_admin() {
  check_env
  python3 -c "
import sys, os, getpass
sys.path.insert(0, '.')
from webapp.database import init_db
from webapp.models import User
from webapp.auth import hash_password
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

init_db()
engine = create_engine('sqlite:///webapp/daily_paper.db')
Session = sessionmaker(bind=engine)
db = Session()

username = input('用户名: ').strip()
if not username:
    print('用户名不能为空'); sys.exit(1)
if db.query(User).filter_by(username=username).first():
    print(f'用户 {username} 已存在'); sys.exit(1)

password = getpass.getpass('密码: ')
if len(password) < 6:
    print('密码至少 6 位'); sys.exit(1)

u = User(username=username, password_hash=hash_password(password), is_admin=True, is_active=True)
db.add(u)
db.commit()
print(f'管理员账号 [{username}] 创建成功')
"
}

mkdir -p "$SCRIPT_DIR/logs"

case "${1:-}" in
  --dev)          start_webapp --dev ;;
  --android)      start_expo development ;;
  --android-prod) start_expo production ;;
  --all)          start_webapp; start_expo development ;;
  --stop)      stop_services ;;
  --status)    show_status ;;
  --create-admin) create_admin ;;
  -h|--help)   usage ;;
  "")          start_webapp ;;
  *)           echo "未知选项: $1"; usage ;;
esac
