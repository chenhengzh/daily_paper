import json
import os
import sys
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from webapp.database import get_db
from webapp.models import User, Paper, DailyJob, UserPaperResult, ChatMessage
from webapp.auth import get_current_user

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

router = APIRouter()

_TMPL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=_TMPL_DIR)

# In-memory progress store: user_id -> list of progress event dicts
_trigger_progress: dict[int, list] = {}
_trigger_done: dict[int, bool] = {}


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
    from datetime import timedelta
    from webapp.services.pipeline import scrape_and_store, rate_papers_for_user

    user = _current_user_dep(request, db)
    body = await request.json()
    force = bool(body.get("force", False))
    user_id = user.id

    # Reset progress for this user
    _trigger_progress[user_id] = []
    _trigger_done[user_id] = False

    def _push(event: dict):
        _trigger_progress.setdefault(user_id, []).append(event)

    def _run_in_thread():
        logger = logging.getLogger("trigger")
        try:
            import src.remote_llm_api as llm_mod
            llm_mod._DEFAULT_SEMAPHORE = asyncio.Semaphore(llm_mod._DEFAULT_CONFIG.MAX_CONCURRENCY)
            llm_mod._DEFAULT_RATE_LIMITER = llm_mod.AsyncQpmRateLimiter(llm_mod._DEFAULT_CONFIG.QPM)
            llm_mod._DEFAULT_CLIENT = None

            from datetime import date as _date
            from webapp.models import UserConfig as _UserConfig
            _db2 = __import__('webapp.database', fromlist=['SessionLocal']).SessionLocal()
            try:
                _cfg = _db2.query(_UserConfig).filter(_UserConfig.user_id == user_id).first()
                _keywords = json.loads(_cfg.keywords_json or "[]") if _cfg else None
                _categories = json.loads(_cfg.categories_json or "[]") if _cfg else None
                _max_results = _cfg.max_results if _cfg else 800
            finally:
                _db2.close()
            today = _date.today()

            async def _run_all():
                processed = 0
                for i in range(5):
                    d = today - timedelta(days=i)
                    _push({"type": "scraping", "date": d.isoformat(), "step": i + 1})
                    logger.info(f"[trigger] 抓取 {d}")
                    raw = scrape_and_store(d, max_results=_max_results, keywords=_keywords, categories=_categories)
                    from webapp.database import SessionLocal as _SL
                    from webapp.models import Paper as _Paper
                    _db = _SL()
                    try:
                        has_papers = _db.query(_Paper.id).filter(_Paper.paper_date == d).first() is not None
                    finally:
                        _db.close()
                    if raw or has_papers:
                        _push({"type": "rating", "date": d.isoformat(), "count": len(raw) if raw else 0})
                        await rate_papers_for_user(user_id, d, force=force)
                        _push({"type": "done_date", "date": d.isoformat()})
                        processed += 1
                    else:
                        _push({"type": "skip", "date": d.isoformat()})
                        logger.info(f"[trigger] {d} 无数据，跳过")
                _push({"type": "all_done", "processed": processed})

            asyncio.run(_run_all())
            logger.info(f"[trigger] 全部完成 user_id={user_id}")
        except Exception as e:
            logger.exception(f"[trigger] 任务失败: {e}")
            _push({"type": "error", "message": str(e)})
        finally:
            _trigger_done[user_id] = True

    t = threading.Thread(target=_run_in_thread, daemon=True)
    t.start()

    return {"status": "triggered", "user": user.username}


@router.get("/trigger/status", response_class=JSONResponse)
async def trigger_status(request: Request, db: Session = Depends(get_db)):
    """Return whether a trigger job is currently running for the user."""
    user = _current_user_dep(request, db)
    user_id = user.id
    running = user_id in _trigger_progress and not _trigger_done.get(user_id, True)
    return {"running": running}


@router.get("/trigger/progress")
async def trigger_progress(request: Request, db: Session = Depends(get_db)):
    """SSE stream of trigger progress events for the current user."""
    import asyncio as _asyncio

    user = _current_user_dep(request, db)
    user_id = user.id

    async def event_stream():
        sent = 0
        while True:
            events = _trigger_progress.get(user_id, [])
            while sent < len(events):
                evt = events[sent]
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                sent += 1
                if evt.get("type") in ("all_done", "error"):
                    return
            if _trigger_done.get(user_id) and sent >= len(_trigger_progress.get(user_id, [])):
                yield f"data: {json.dumps({'type': 'all_done', 'processed': 0})}\n\n"
                return
            await _asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{arxiv_id}/chat/history", response_class=JSONResponse)
async def paper_chat_history(arxiv_id: str, request: Request, db: Session = Depends(get_db)):
    """获取当前用户对该论文的历史聊天记录。"""
    user = _current_user_dep(request, db)
    paper = db.query(Paper).filter(Paper.arxiv_id == arxiv_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id, ChatMessage.paper_id == paper.id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in msgs]


@router.post("/{arxiv_id}/chat")
async def paper_chat(arxiv_id: str, request: Request, db: Session = Depends(get_db)):
    """流式 SSE：接收用户消息，流式返回 AI 回复，并持久化对话记录。
    Body: { "content": "用户输入的消息" }
    """
    from remote_llm_api import default_chat_completion_stream

    user = _current_user_dep(request, db)
    body = await request.json()
    user_content = body.get("content", "").strip()
    if not user_content:
        raise HTTPException(status_code=400, detail="消息不能为空")

    paper = db.query(Paper).filter(Paper.arxiv_id == arxiv_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    result = (
        db.query(UserPaperResult)
        .filter(UserPaperResult.user_id == user.id, UserPaperResult.paper_id == paper.id)
        .first()
    )

    # 构建 system prompt
    authors = ", ".join(json.loads(paper.authors_json or "[]")[:5])
    tldr_zh = (result.tldr_zh or "") if result else ""
    score = f"{result.overall_priority_score:.1f}" if result and result.overall_priority_score else "N/A"
    system_prompt = f"""你是一个论文阅读助手。以下是读者正在阅读的论文：

标题：{paper.title}
作者：{authors}
摘要：{paper.summary}
中文摘要：{tldr_zh}
综合评分：{score}

请根据以上信息回答读者的问题，可以用中文回复。"""

    # 加载历史记录
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id, ChatMessage.paper_id == paper.id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    messages = (
        [{"role": "system", "content": system_prompt}]
        + [{"role": m.role, "content": m.content} for m in history]
        + [{"role": "user", "content": user_content}]
    )

    # 保存用户消息
    db.add(ChatMessage(user_id=user.id, paper_id=paper.id, role="user", content=user_content))
    db.commit()

    paper_id = paper.id
    user_id = user.id

    async def stream_and_save():
        from webapp.database import SessionLocal
        collected = []
        try:
            async for chunk in default_chat_completion_stream(
                namespace="paper_chat",
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
            ):
                collected.append(chunk)
                # SSE 格式：data: <chunk>\n\n
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps('[ERROR] ' + str(e))}\n\n"
        finally:
            # 流结束后保存完整 AI 回复
            full_reply = "".join(collected)
            if full_reply:
                save_db = SessionLocal()
                try:
                    save_db.add(ChatMessage(
                        user_id=user_id, paper_id=paper_id,
                        role="assistant", content=full_reply,
                    ))
                    save_db.commit()
                finally:
                    save_db.close()
            yield "data: [DONE]\n\n"

    return StreamingResponse(stream_and_save(), media_type="text/event-stream")


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
