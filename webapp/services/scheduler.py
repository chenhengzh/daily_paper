import logging
from datetime import datetime, date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from webapp.services.pipeline import run_daily_pipeline

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def _daily_job():
    today = datetime.now().astimezone().date()
    logger.info(f"[scheduler] 定时任务触发，处理日期: {today}")
    # 处理今天和昨天（防止昨天因网络问题漏跑）
    for delta in [1, 0]:
        target = today - timedelta(days=delta)
        try:
            await run_daily_pipeline(target_date=target, force=False)
        except Exception as e:
            logger.error(f"[scheduler] pipeline 失败 date={target}: {e}")


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(
        _daily_job,
        CronTrigger(hour=9, minute=30, day_of_week="mon-fri"),
        id="daily_paper_job",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("[scheduler] APScheduler 已启动，工作日每天 09:30 (CST) 触发")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[scheduler] APScheduler 已停止")
