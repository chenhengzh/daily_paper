import json
import os
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from webapp.database import get_db
from webapp.models import User, Paper, DailyJob, UserPaperResult
from webapp.auth import get_current_user

router = APIRouter()

_TMPL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=_TMPL_DIR)


def _tmpl(request, name, ctx=None, **kwargs):
    ctx = ctx or {}
    ctx["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=ctx, **kwargs)


def _current_user_dep(request: Request, db: Session = Depends(get_db)) -> User:
    return get_current_user(request, db)


@router.get("/", response_class=HTMLResponse)
async def papers_page(
    request: Request,
    date_str: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/auth/login", status_code=302)

    # 获取用户有数据的日期列表（用于导航）
    dates = _get_user_dates(user.id, db)

    # 若未指定日期，默认选最近一次有数据的日期；否则用指定日期
    if date_str:
        target_date = _parse_date(date_str)
    elif dates:
        target_date = dates[0]
    else:
        target_date = _parse_date(None)

    return _tmpl(request, "index.html", {
        "user": user,
        "target_date": target_date.isoformat(),
        "dates": [d.isoformat() for d in dates],
    })


@router.get("/api", response_class=JSONResponse)
async def papers_api(
    request: Request,
    date_str: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
):
    """返回指定日期该用户的所有论文评分数据（前端一次性加载后本地筛选）。"""
    user = _current_user_dep(request, db)
    target_date = _parse_date(date_str)

    job = db.query(DailyJob).filter(
        DailyJob.user_id == user.id,
        DailyJob.job_date == target_date,
    ).first()

    job_info = None
    if job:
        job_info = {
            "status": job.status,
            "scrape_count": job.scrape_count,
            "rated_count": job.rated_count,
            "kept_count": job.kept_count,
            "high_priority_count": job.high_priority_count,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error_msg": job.error_msg,
        }

    # 联查 Paper + UserPaperResult
    rows = (
        db.query(UserPaperResult, Paper)
        .join(Paper, UserPaperResult.paper_id == Paper.id)
        .filter(
            UserPaperResult.user_id == user.id,
            Paper.paper_date == target_date,
        )
        .all()
    )

    papers = []
    for result, paper in rows:
        papers.append({
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "summary": paper.summary,
            "url": paper.abs_url or paper.url,
            "pdf_url": paper.pdf_url,
            "authors": json.loads(paper.authors_json or "[]"),
            "categories": json.loads(paper.categories_json or "[]"),
            "published_date": paper.published_date.isoformat() if paper.published_date else None,
            # 评分字段
            "keep": result.keep,
            "keep_reason": result.keep_reason,
            "interest_field": result.interest_field,
            "interest_subfield": result.interest_subfield,
            "tldr": result.tldr,
            "tldr_zh": result.tldr_zh,
            "tags": json.loads(result.tags_json or "[]"),
            "relevance_score": result.relevance_score,
            "quality_score": result.quality_score,
            "novelty_claim_score": result.novelty_claim_score,
            "clarity_score": result.clarity_score,
            "potential_impact_score": result.potential_impact_score,
            "overall_priority_score": result.overall_priority_score,
            "tier": result.tier,
            "high_priority": result.high_priority,
            "high_priority_rank": result.high_priority_rank,
            "signal_high_keywords": json.loads(result.signal_high_keywords_json or "[]"),
            "signal_notable_authors": json.loads(result.signal_notable_authors_json or "[]"),
            "signal_low_keywords": json.loads(result.signal_low_keywords_json or "[]"),
        })

    # 按 overall_priority_score 降序
    papers.sort(key=lambda x: (x.get("overall_priority_score") or 0), reverse=True)

    return {"date": target_date.isoformat(), "job": job_info, "papers": papers}


@router.get("/dates", response_class=JSONResponse)
async def papers_dates(request: Request, db: Session = Depends(get_db)):
    user = _current_user_dep(request, db)
    dates = _get_user_dates(user.id, db)
    return [d.isoformat() for d in dates]


@router.get("/summary", response_class=JSONResponse)
async def papers_summary(
    request: Request,
    date_str: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
):
    user = _current_user_dep(request, db)
    target_date = _parse_date(date_str)

    job = db.query(DailyJob).filter(
        DailyJob.user_id == user.id,
        DailyJob.job_date == target_date,
    ).first()

    if not job:
        return {"date": target_date.isoformat(), "daily_summary_zh": "", "daily_ideas_zh": ""}

    return {
        "date": target_date.isoformat(),
        "daily_summary_zh": job.daily_summary_zh or "",
        "daily_ideas_zh": job.daily_ideas_zh or "",
    }


@router.get("/{arxiv_id}", response_class=JSONResponse)
async def paper_detail(arxiv_id: str, request: Request, db: Session = Depends(get_db)):
    user = _current_user_dep(request, db)
    paper = db.query(Paper).filter(Paper.arxiv_id == arxiv_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    result = (
        db.query(UserPaperResult)
        .filter(UserPaperResult.user_id == user.id, UserPaperResult.paper_id == paper.id)
        .first()
    )

    data = {
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "summary": paper.summary,
        "url": paper.abs_url or paper.url,
        "pdf_url": paper.pdf_url,
        "authors": json.loads(paper.authors_json or "[]"),
        "categories": json.loads(paper.categories_json or "[]"),
        "published_date": paper.published_date.isoformat() if paper.published_date else None,
    }
    if result:
        data.update({
            "keep": result.keep,
            "keep_reason": result.keep_reason,
            "interest_field": result.interest_field,
            "interest_subfield": result.interest_subfield,
            "interest_match_reason": result.interest_match_reason,
            "tldr": result.tldr,
            "tldr_zh": result.tldr_zh,
            "tags": json.loads(result.tags_json or "[]"),
            "relevance_score": result.relevance_score,
            "quality_score": result.quality_score,
            "novelty_claim_score": result.novelty_claim_score,
            "clarity_score": result.clarity_score,
            "potential_impact_score": result.potential_impact_score,
            "overall_priority_score": result.overall_priority_score,
            "tier": result.tier,
            "high_priority": result.high_priority,
            "high_priority_rank": result.high_priority_rank,
            "signal_high_keywords": json.loads(result.signal_high_keywords_json or "[]"),
            "signal_notable_authors": json.loads(result.signal_notable_authors_json or "[]"),
            "signal_low_keywords": json.loads(result.signal_low_keywords_json or "[]"),
            "signal_evidence_keywords": json.loads(result.signal_evidence_keywords_json or "[]"),
        })
    return data


@router.post("/trigger", response_class=JSONResponse)
async def trigger_job(
    request: Request,
    db: Session = Depends(get_db),
):
    import threading
    import asyncio
    import logging
    from webapp.services.pipeline import scrape_and_store, rate_papers_for_user

    user = _current_user_dep(request, db)
    body = await request.json()
    date_str = body.get("date")
    force = bool(body.get("force", False))
    target_date = _parse_date(date_str)
    user_id = user.id

    def _run_in_thread():
        logger = logging.getLogger("trigger")
        try:
            logger.info(f"[trigger] 开始抓取 {target_date}")
            raw = scrape_and_store(target_date)

            # 如果当天 arXiv 尚无数据，回退到数据库中最近一次有论文的日期
            actual_date = target_date
            if not raw:
                from webapp.database import SessionLocal as _SL
                from webapp.models import Paper as _Paper
                _db = _SL()
                try:
                    latest = (
                        _db.query(_Paper.paper_date)
                        .order_by(_Paper.paper_date.desc())
                        .first()
                    )
                    if latest:
                        actual_date = latest.paper_date
                        logger.info(f"[trigger] 当天无数据，回退到 {actual_date}")
                finally:
                    _db.close()

            logger.info(f"[trigger] 抓取完成，开始评分 user_id={user_id} date={actual_date}")
            asyncio.run(rate_papers_for_user(user_id, actual_date, force=force))
            logger.info(f"[trigger] 全部完成 user_id={user_id} date={actual_date}")
        except Exception as e:
            logger.exception(f"[trigger] 任务失败: {e}")

    t = threading.Thread(target=_run_in_thread, daemon=True)
    t.start()

    return {"status": "triggered", "date": target_date.isoformat(), "user": user.username}


@router.post("/{arxiv_id}/chat", response_class=JSONResponse)
async def paper_chat(arxiv_id: str, request: Request, db: Session = Depends(get_db)):
    """与 LLM 讨论指定论文。Body: { messages: [{role, content}, ...] }"""
    import sys, os
    src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from remote_llm_api import default_chat_completion_text

    user = _current_user_dep(request, db)
    body = await request.json()
    user_messages = body.get("messages", [])

    paper = db.query(Paper).filter(Paper.arxiv_id == arxiv_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    result = (
        db.query(UserPaperResult)
        .filter(UserPaperResult.user_id == user.id, UserPaperResult.paper_id == paper.id)
        .first()
    )

    authors = ", ".join(json.loads(paper.authors_json or "[]")[:5])
    tldr_zh = (result.tldr_zh or "") if result else ""
    score = f"{result.overall_priority_score:.1f}" if result and result.overall_priority_score else "N/A"

    system_prompt = f"""你是一个论文阅读助手。以下是读者正在阅读的论文：

标题：{paper.title}
作者：{authors}
摘要：{paper.summary}
中文摘要：{tldr_zh}
综合评分：{score}

请根据以上信息回答读者的问题。可以用中文回复。"""

    messages = [{"role": "system", "content": system_prompt}] + user_messages

    try:
        reply = await default_chat_completion_text(
            namespace="paper_chat",
            messages=messages,
            max_tokens=1024,
            temperature=0.7,
        )
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 工具函数 ────────────────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> date:
    if date_str:
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            pass
    return datetime.now().astimezone().date()


def _get_user_dates(user_id: int, db: Session) -> list[date]:
    rows = (
        db.query(DailyJob.job_date)
        .filter(DailyJob.user_id == user_id, DailyJob.status == "done")
        .order_by(DailyJob.job_date.desc())
        .all()
    )
    return [r.job_date for r in rows]
