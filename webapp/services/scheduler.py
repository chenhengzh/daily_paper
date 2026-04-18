import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from webapp.services.pipeline import run_daily_pipeline, rate_papers_for_user, scrape_and_store
from webapp.database import SessionLocal
from webapp.models import User, UserConfig

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def _check_and_trigger():
    """每分钟检查，对到达触发时间且开启定时的用户执行 pipeline。"""
    now = datetime.now().astimezone()
    today = now.date()

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_active == True).all()
        for user in users:
            cfg = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
            auto_trigger = cfg.auto_trigger if cfg and cfg.auto_trigger is not None else True
            trigger_hour = cfg.trigger_hour if cfg and cfg.trigger_hour is not None else 9
            trigger_minute = cfg.trigger_minute if cfg and cfg.trigger_minute is not None else 30

            if not auto_trigger:
                continue
            if now.hour != trigger_hour or now.minute != trigger_minute:
                continue

            logger.info(f"[scheduler] 触发用户 {user.username} 的定时任务")
            # 先抓取（只需一次，多用户共享）
            import json
            keywords = json.loads(cfg.keywords_json or "[]") if cfg else None
            categories = json.loads(cfg.categories_json or "[]") if cfg else None
            max_results = cfg.max_results if cfg else 800
            for delta in [1, 0]:
                target = today - timedelta(days=delta)
                try:
                    scrape_and_store(target, max_results=max_results, keywords=keywords, categories=categories)
                    await rate_papers_for_user(user.id, target, force=False)
                except Exception as e:
                    logger.error(f"[scheduler] user={user.username} date={target} 失败: {e}")
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
