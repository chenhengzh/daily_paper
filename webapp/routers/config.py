import json
import os
from datetime import datetime

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from webapp.database import get_db
from webapp.models import User, UserConfig
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
async def config_page(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/auth/login", status_code=302)

    cfg = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    cfg_data = _serialize_config(cfg)

    return _tmpl(request, "config.html", {"user": user, "config": cfg_data})


@router.get("/api", response_class=JSONResponse)
async def get_config(request: Request, db: Session = Depends(get_db)):
    user = _current_user_dep(request, db)
    cfg = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    return _serialize_config(cfg)


@router.put("/api", response_class=JSONResponse)
async def update_config(request: Request, db: Session = Depends(get_db)):
    user = _current_user_dep(request, db)
    body = await request.json()

    cfg = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if not cfg:
        cfg = UserConfig(user_id=user.id)
        db.add(cfg)

    if "keywords" in body:
        cfg.keywords_json = json.dumps(body["keywords"], ensure_ascii=False)
    if "categories" in body:
        cfg.categories_json = json.dumps(body["categories"], ensure_ascii=False)
    if "interests_text" in body:
        cfg.interests_text = str(body["interests_text"])
    if "interest_table" in body:
        cfg.interest_table_json = json.dumps(body["interest_table"], ensure_ascii=False)
    if "high_signal_keywords" in body:
        cfg.high_signal_keywords_json = json.dumps(body["high_signal_keywords"], ensure_ascii=False)
    if "low_signal_keywords" in body:
        cfg.low_signal_keywords_json = json.dumps(body["low_signal_keywords"], ensure_ascii=False)
    if "notable_authors" in body:
        cfg.notable_authors_json = json.dumps(body["notable_authors"], ensure_ascii=False)
    if "llm_api_key" in body:
        cfg.llm_api_key = body["llm_api_key"] or None
    if "llm_endpoint" in body:
        cfg.llm_endpoint = body["llm_endpoint"] or None
    if "llm_model" in body:
        cfg.llm_model = body["llm_model"] or None
    if "max_results" in body:
        cfg.max_results = int(body["max_results"] or 800)
    if "high_priority_target" in body:
        cfg.high_priority_target = int(body["high_priority_target"] or 15)

    cfg.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@router.get("/defaults", response_class=JSONResponse)
async def get_defaults(request: Request, db: Session = Depends(get_db)):
    _current_user_dep(request, db)
    import sys, os as _os
    src_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from src.filter import DEFAULT_INTERESTS, INTEREST_TABLE, HIGH_SIGNAL_KEYWORDS, LOW_SIGNAL_KEYWORDS, NOTABLE_AUTHORS
    from src.scraper import DEFAULT_CATEGORIES
    from src.filter import DEFAULT_ARXIV_KEYWORDS

    return {
        "keywords": DEFAULT_ARXIV_KEYWORDS,
        "categories": DEFAULT_CATEGORIES,
        "interests_text": DEFAULT_INTERESTS,
        "interest_table": INTEREST_TABLE,
        "high_signal_keywords": HIGH_SIGNAL_KEYWORDS,
        "low_signal_keywords": LOW_SIGNAL_KEYWORDS,
        "notable_authors": sorted(NOTABLE_AUTHORS),
        "max_results": 800,
        "high_priority_target": 15,
    }


def _serialize_config(cfg: UserConfig | None) -> dict:
    if cfg is None:
        return {
            "keywords": [],
            "categories": [],
            "interests_text": "",
            "interest_table": [],
            "high_signal_keywords": [],
            "low_signal_keywords": [],
            "notable_authors": [],
            "llm_api_key": "",
            "llm_endpoint": "",
            "llm_model": "",
            "max_results": 800,
            "high_priority_target": 15,
        }
    return {
        "keywords": json.loads(cfg.keywords_json or "[]"),
        "categories": json.loads(cfg.categories_json or "[]"),
        "interests_text": cfg.interests_text or "",
        "interest_table": json.loads(cfg.interest_table_json or "[]"),
        "high_signal_keywords": json.loads(cfg.high_signal_keywords_json or "[]"),
        "low_signal_keywords": json.loads(cfg.low_signal_keywords_json or "[]"),
        "notable_authors": json.loads(cfg.notable_authors_json or "[]"),
        "llm_api_key": cfg.llm_api_key or "",
        "llm_endpoint": cfg.llm_endpoint or "",
        "llm_model": cfg.llm_model or "",
        "max_results": cfg.max_results,
        "high_priority_target": cfg.high_priority_target,
    }
