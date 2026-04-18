"""
论文处理 pipeline：抓取 → 评分 → 入库
复用 src/ 中的核心模块，通过临时注入用户配置实现个性化评分。
"""
import json
import logging
import asyncio
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from webapp.models import Paper, DailyJob, UserPaperResult, User, UserConfig
from webapp.database import SessionLocal

logger = logging.getLogger(__name__)


def _load_src():
    """延迟导入 src 模块（避免循环依赖和启动时 import 失败）。"""
    import sys, os
    src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)


def scrape_and_store(
    target_date: date,
    max_results: int = 800,
    keywords: list[str] | None = None,
    categories: list[str] | None = None,
) -> list[dict]:
    """全局抓取：从 arXiv 抓取指定日期的论文并存入 papers 表。幂等（upsert）。"""
    _load_src()
    from scraper import fetch_daily_papers

    logger.info(f"[pipeline] 开始抓取 {target_date.isoformat()}")
    raw_papers = fetch_daily_papers(
        specified_date=target_date,
        max_results=max_results,
        keywords=keywords,
        categories=categories,
    )
    logger.info(f"[pipeline] 抓取到 {len(raw_papers)} 篇")

    if not raw_papers:
        return []

    db = SessionLocal()
    try:
        for p in raw_papers:
            published = p.get("published_date")
            updated = p.get("updated_date")
            if isinstance(published, datetime) and published.tzinfo:
                published = published.astimezone(timezone.utc).replace(tzinfo=None)
            if isinstance(updated, datetime) and updated.tzinfo:
                updated = updated.astimezone(timezone.utc).replace(tzinfo=None)

            stmt = sqlite_insert(Paper).values(
                arxiv_id=p.get("arxiv_id") or "",
                title=p.get("title") or "",
                summary=p.get("summary") or "",
                url=p.get("url") or "",
                abs_url=p.get("abs_url") or "",
                pdf_url=p.get("pdf_url"),
                published_date=published,
                updated_date=updated,
                categories_json=json.dumps(p.get("categories") or [], ensure_ascii=False),
                authors_json=json.dumps(p.get("authors") or [], ensure_ascii=False),
                paper_date=target_date,
            ).on_conflict_do_nothing(index_elements=["arxiv_id"])
            db.execute(stmt)
        db.commit()
    finally:
        db.close()

    return raw_papers


async def rate_papers_for_user(
    user_id: int,
    target_date: date,
    force: bool = False,
) -> None:
    """为指定用户对指定日期的论文做评分，结果存入 user_paper_results 表。"""
    _load_src()
    import src.filter as filter_mod
    from src.filter import _rate_papers_async, _postprocess_scoring
    from src.main import mark_high_priority, generate_daily_summary_zh, generate_future_ideas_zh

    # 重置 remote_llm_api 的 asyncio 对象，确保它们绑定到当前事件循环。
    # 当本函数通过 asyncio.run() 在后台线程中运行时，模块级别的 Semaphore/Lock
    # 是在主线程的事件循环中创建的，直接使用会报错。
    import src.remote_llm_api as llm_mod
    llm_mod._DEFAULT_SEMAPHORE = asyncio.Semaphore(llm_mod._DEFAULT_CONFIG.MAX_CONCURRENCY)
    llm_mod._DEFAULT_RATE_LIMITER = llm_mod.AsyncQpmRateLimiter(llm_mod._DEFAULT_CONFIG.QPM)
    llm_mod._DEFAULT_CLIENT = None  # 强制重建 client（AsyncOpenAI 也绑定了事件循环）

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning(f"[pipeline] user_id={user_id} 不存在")
            return

        # 获取或创建 DailyJob
        job = db.query(DailyJob).filter(
            DailyJob.user_id == user_id,
            DailyJob.job_date == target_date,
        ).first()

        if job is None:
            job = DailyJob(user_id=user_id, job_date=target_date, status="pending")
            db.add(job)
            db.commit()
            db.refresh(job)

        if job.status == "done" and not force:
            logger.info(f"[pipeline] user={user.username} date={target_date} 已完成，跳过")
            return

        job.status = "rating"
        job.started_at = datetime.utcnow()
        job.error_msg = None
        db.commit()

        # 读取该日期的所有论文
        papers_orm = db.query(Paper).filter(Paper.paper_date == target_date).all()
        if not papers_orm:
            logger.warning(f"[pipeline] {target_date} 无论文数据，请先执行抓取")
            job.status = "failed"
            job.error_msg = "no papers for this date"
            db.commit()
            return

        job.scrape_count = len(papers_orm)
        db.commit()

        # 将 ORM 对象转为 dict（供 filter.py 使用）
        papers_dict = []
        for p in papers_orm:
            papers_dict.append({
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "summary": p.summary,
                "url": p.url,
                "abs_url": p.abs_url,
                "pdf_url": p.pdf_url,
                "published_date": p.published_date,
                "updated_date": p.updated_date,
                "categories": json.loads(p.categories_json or "[]"),
                "authors": json.loads(p.authors_json or "[]"),
            })

        # 读取用户配置
        cfg = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
        # Build interests_text from interest_table ({name, description} format)
        interests_text = filter_mod.DEFAULT_INTERESTS
        if cfg:
            items = json.loads(cfg.interest_table_json or "[]")
            if items and isinstance(items[0], dict) and "name" in items[0]:
                interests_text = "\n".join(
                    f"- {it['name']}: {it.get('description', '')}" for it in items
                )
            elif cfg.interests_text:
                interests_text = cfg.interests_text
        notable_authors = set(json.loads(cfg.notable_authors_json or "[]")) if cfg else filter_mod.NOTABLE_AUTHORS
        high_signal = json.loads(cfg.high_signal_keywords_json or "[]") if cfg else filter_mod.HIGH_SIGNAL_KEYWORDS
        low_signal = []  # low signal keywords removed from UI
        hp_target = cfg.high_priority_target if cfg else 15

        # 临时注入用户配置（asyncio 单线程安全）
        orig_notable = filter_mod.NOTABLE_AUTHORS
        orig_high = filter_mod.HIGH_SIGNAL_KEYWORDS
        orig_low = filter_mod.LOW_SIGNAL_KEYWORDS
        try:
            filter_mod.NOTABLE_AUTHORS = notable_authors
            filter_mod.HIGH_SIGNAL_KEYWORDS = high_signal
            filter_mod.LOW_SIGNAL_KEYWORDS = low_signal

            rated = await _rate_papers_async(papers_dict, interests_text)
        finally:
            filter_mod.NOTABLE_AUTHORS = orig_notable
            filter_mod.HIGH_SIGNAL_KEYWORDS = orig_high
            filter_mod.LOW_SIGNAL_KEYWORDS = orig_low

        rated = _postprocess_scoring(rated)
        rated = mark_high_priority(rated)

        # 生成当日总结
        daily_summary_zh = ""
        daily_ideas_zh = ""
        try:
            daily_summary_zh, daily_ideas_zh = await asyncio.gather(
                generate_daily_summary_zh(target_date=target_date, papers=rated),
                generate_future_ideas_zh(target_date=target_date, papers=rated),
            )
        except Exception as e:
            logger.warning(f"[pipeline] 生成总结失败（忽略）: {e}")

        # 将评分结果写入 user_paper_results
        paper_id_map = {p.arxiv_id: p.id for p in papers_orm}
        kept_count = 0
        hp_count = 0

        for r in rated:
            arxiv_id = r.get("arxiv_id") or ""
            paper_id = paper_id_map.get(arxiv_id)
            if not paper_id:
                continue

            if r.get("keep", True):
                kept_count += 1
            if r.get("high_priority"):
                hp_count += 1

            stmt = sqlite_insert(UserPaperResult).values(
                user_id=user_id,
                paper_id=paper_id,
                job_id=job.id,
                keep=bool(r.get("keep", True)),
                keep_reason=r.get("keep_reason") or "",
                interest_field=r.get("interest_field") or "",
                interest_subfield=r.get("interest_subfield") or "",
                interest_match_reason=r.get("interest_match_reason") or "",
                tldr=r.get("tldr") or "",
                tldr_zh=r.get("tldr_zh") or "",
                tags_json=json.dumps(r.get("tags") or [], ensure_ascii=False),
                relevance_score=r.get("relevance_score"),
                quality_score=r.get("quality_score"),
                novelty_claim_score=r.get("novelty_claim_score"),
                clarity_score=r.get("clarity_score"),
                potential_impact_score=r.get("potential_impact_score"),
                overall_priority_score=r.get("overall_priority_score"),
                tier=r.get("tier") or "C",
                high_priority=bool(r.get("high_priority", False)),
                high_priority_rank=r.get("high_priority_rank"),
                signal_high_keywords_json=json.dumps(r.get("signal_high_keywords") or [], ensure_ascii=False),
                signal_notable_authors_json=json.dumps(r.get("signal_notable_authors") or [], ensure_ascii=False),
                signal_low_keywords_json=json.dumps(r.get("signal_low_keywords") or [], ensure_ascii=False),
                signal_evidence_keywords_json=json.dumps(r.get("signal_evidence_keywords") or [], ensure_ascii=False),
            ).on_conflict_do_update(
                index_elements=["user_id", "paper_id"],
                set_={
                    "job_id": job.id,
                    "keep": bool(r.get("keep", True)),
                    "keep_reason": r.get("keep_reason") or "",
                    "interest_field": r.get("interest_field") or "",
                    "interest_subfield": r.get("interest_subfield") or "",
                    "interest_match_reason": r.get("interest_match_reason") or "",
                    "tldr": r.get("tldr") or "",
                    "tldr_zh": r.get("tldr_zh") or "",
                    "tags_json": json.dumps(r.get("tags") or [], ensure_ascii=False),
                    "relevance_score": r.get("relevance_score"),
                    "quality_score": r.get("quality_score"),
                    "novelty_claim_score": r.get("novelty_claim_score"),
                    "clarity_score": r.get("clarity_score"),
                    "potential_impact_score": r.get("potential_impact_score"),
                    "overall_priority_score": r.get("overall_priority_score"),
                    "tier": r.get("tier") or "C",
                    "high_priority": bool(r.get("high_priority", False)),
                    "high_priority_rank": r.get("high_priority_rank"),
                    "signal_high_keywords_json": json.dumps(r.get("signal_high_keywords") or [], ensure_ascii=False),
                    "signal_notable_authors_json": json.dumps(r.get("signal_notable_authors") or [], ensure_ascii=False),
                    "signal_low_keywords_json": json.dumps(r.get("signal_low_keywords") or [], ensure_ascii=False),
                    "signal_evidence_keywords_json": json.dumps(r.get("signal_evidence_keywords") or [], ensure_ascii=False),
                },
            )
            db.execute(stmt)

        job.rated_count = len(rated)
        job.kept_count = kept_count
        job.high_priority_count = hp_count
        job.daily_summary_zh = daily_summary_zh or ""
        job.daily_ideas_zh = daily_ideas_zh or ""
        job.status = "done"
        job.finished_at = datetime.utcnow()
        db.commit()
        logger.info(f"[pipeline] user={user.username} date={target_date} 完成，共 {len(rated)} 篇，kept={kept_count}，hp={hp_count}")

    except Exception as e:
        logger.exception(f"[pipeline] user_id={user_id} date={target_date} 失败: {e}")
        try:
            job = db.query(DailyJob).filter(
                DailyJob.user_id == user_id, DailyJob.job_date == target_date
            ).first()
            if job:
                job.status = "failed"
                job.error_msg = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def run_daily_pipeline(target_date: date, force: bool = False) -> None:
    """全局 pipeline：先抓取，再并发为所有活跃用户评分。"""
    _load_src()
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_active == True).all()
        user_ids = [u.id for u in users]
    finally:
        db.close()

    if not user_ids:
        logger.info("[pipeline] 没有活跃用户，跳过")
        return

    # 阶段1：全局抓取（取第一个用户的配置）
    db = SessionLocal()
    try:
        cfg = db.query(UserConfig).filter(UserConfig.user_id == user_ids[0]).first()
        max_results = cfg.max_results if cfg else 800
        keywords = json.loads(cfg.keywords_json or "[]") if cfg else None
        categories = json.loads(cfg.categories_json or "[]") if cfg else None
    finally:
        db.close()

    scrape_and_store(target_date, max_results=max_results, keywords=keywords, categories=categories)

    # 阶段2：并发为每个用户评分
    tasks = [rate_papers_for_user(uid, target_date, force=force) for uid in user_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for uid, res in zip(user_ids, results):
        if isinstance(res, Exception):
            logger.error(f"[pipeline] user_id={uid} 评分异常: {res}")
