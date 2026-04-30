import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from webapp.services.pipeline import rate_papers_for_user, scrape_and_store
from webapp.database import SessionLocal
from webapp.models import User, UserConfig

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

# 记录正在后台运行的用户，避免同一用户重复触发
_running_users: set[int] = set()


def _run_user_pipeline(user_id: int, username: str, today, keywords, categories, max_results):
    """在独立线程+事件循环中跑单个用户的 pipeline，不阻塞 scheduler。"""
    async def _run():
        for i in range(5):
            target = today - timedelta(days=i)
            try:
                scrape_and_store(target, max_results=max_results, keywords=keywords, categories=categories)
                await rate_papers_for_user(user_id, target, force=False)
            except Exception as e:
                logger.error(f"[scheduler] user={username} date={target} 失败: {e}")

    try:
        asyncio.run(_run())
    finally:
        _running_users.discard(user_id)
        logger.info(f"[scheduler] user={username} pipeline 完成")


async def _check_and_trigger():
    """每分钟检查，对到达触发时间且开启定时的用户，在独立线程中启动 pipeline。"""
    now = datetime.now().astimezone()
    # 18点为分界线：18点前最新可用日期为前天，18点及之后为昨天
    if now.hour < 18:
        today = now.date() - timedelta(days=2)
    else:
        today = now.date() - timedelta(days=1)

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_active == True).all()
        for user in users:
            if user.username == "admin":
                continue
            cfg = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
            auto_trigger = cfg.auto_trigger if cfg and cfg.auto_trigger is not None else False
            trigger_hour = cfg.trigger_hour if cfg and cfg.trigger_hour is not None else 18
            trigger_minute = cfg.trigger_minute if cfg and cfg.trigger_minute is not None else 0

            if not auto_trigger:
                continue
            if now.hour != trigger_hour or now.minute != trigger_minute:
                continue
            if user.id in _running_users:
                logger.info(f"[scheduler] user={user.username} 上次任务仍在运行，跳过")
                continue

            logger.info(f"[scheduler] 触发用户 {user.username} 的定时任务")
            _running_users.add(user.id)
            keywords = json.loads(cfg.keywords_json or "[]") if cfg else None
            categories = json.loads(cfg.categories_json or "[]") if cfg else None
            max_results = cfg.max_results if cfg else 800
            t = threading.Thread(
                target=_run_user_pipeline,
                args=(user.id, user.username, today, keywords, categories, max_results),
                daemon=True,
            )
            t.start()
    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(
        _check_and_trigger,
        CronTrigger(minute="*"),
        id="daily_paper_job",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info("[scheduler] APScheduler 已启动，每分钟检查用户定时配置")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[scheduler] APScheduler 已停止")
