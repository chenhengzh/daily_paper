import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from webapp.database import get_db
from webapp.models import User, DailyJob
from webapp.auth import get_current_user

router = APIRouter()

_TMPL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=_TMPL_DIR)


def _tmpl(request, name, ctx=None, **kwargs):
    ctx = ctx or {}
    ctx["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=ctx, **kwargs)


def _require_admin(request: Request, db: Session) -> User:
    try:
        user = get_current_user(request, db)
    except HTTPException:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


@router.get("/", response_class=HTMLResponse)
async def logs_page(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/auth/login", status_code=302)
    if not user.is_admin:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/papers/", status_code=302)
    return _tmpl(request, "logs.html", {"user": user})


@router.get("/api/stats", response_class=JSONResponse)
async def get_stats(request: Request, days: int = 30, db: Session = Depends(get_db)):
    _require_admin(request, db)

    since = datetime.utcnow().date() - timedelta(days=days)

    # Per-user aggregated stats
    rows = (
        db.query(
            User.id,
            User.username,
            User.user_type,
            func.count(DailyJob.id).label("job_count"),
            func.sum(DailyJob.input_tokens).label("total_input"),
            func.sum(DailyJob.output_tokens).label("total_output"),
            func.sum(DailyJob.rated_count).label("total_rated"),
            func.max(DailyJob.job_date).label("last_job_date"),
        )
        .outerjoin(DailyJob, (DailyJob.user_id == User.id) & (DailyJob.job_date >= since))
        .filter(User.is_active == True)
        .group_by(User.id)
        .all()
    )

    users_stats = []
    for r in rows:
        users_stats.append({
            "user_id": r.id,
            "username": r.username,
            "user_type": r.user_type,
            "job_count": r.job_count or 0,
            "total_input_tokens": int(r.total_input or 0),
            "total_output_tokens": int(r.total_output or 0),
            "total_tokens": int((r.total_input or 0) + (r.total_output or 0)),
            "total_rated": int(r.total_rated or 0),
            "last_job_date": str(r.last_job_date) if r.last_job_date else None,
        })

    # Per-day totals for chart
    daily_rows = (
        db.query(
            DailyJob.job_date,
            func.sum(DailyJob.input_tokens).label("input"),
            func.sum(DailyJob.output_tokens).label("output"),
            func.count(DailyJob.id).label("jobs"),
        )
        .filter(DailyJob.job_date >= since)
        .group_by(DailyJob.job_date)
        .order_by(DailyJob.job_date)
        .all()
    )

    daily_stats = [
        {
            "date": str(r.job_date),
            "input_tokens": int(r.input or 0),
            "output_tokens": int(r.output or 0),
            "total_tokens": int((r.input or 0) + (r.output or 0)),
            "jobs": r.jobs,
        }
        for r in daily_rows
    ]

    return {"users": users_stats, "daily": daily_stats, "days": days}


@router.get("/api/jobs", response_class=JSONResponse)
async def get_jobs(
    request: Request,
    user_id: int | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
):
    _require_admin(request, db)

    since = datetime.utcnow().date() - timedelta(days=days)
    q = (
        db.query(DailyJob, User.username)
        .join(User, User.id == DailyJob.user_id)
        .filter(DailyJob.job_date >= since)
    )
    if user_id:
        q = q.filter(DailyJob.user_id == user_id)
    q = q.order_by(DailyJob.job_date.desc(), DailyJob.user_id)

    jobs = []
    for job, username in q.all():
        jobs.append({
            "id": job.id,
            "username": username,
            "job_date": str(job.job_date),
            "status": job.status,
            "scrape_count": job.scrape_count,
            "rated_count": job.rated_count,
            "kept_count": job.kept_count,
            "high_priority_count": job.high_priority_count,
            "input_tokens": job.input_tokens or 0,
            "output_tokens": job.output_tokens or 0,
            "total_tokens": (job.input_tokens or 0) + (job.output_tokens or 0),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error_msg": job.error_msg,
        })

    return {"jobs": jobs}
