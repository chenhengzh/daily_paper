from datetime import datetime
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from webapp.database import get_db
from webapp.models import User, UserConfig
from webapp.auth import hash_password, verify_password
import json, os

router = APIRouter()

_TMPL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=_TMPL_DIR)


def _tmpl(request, name, ctx=None, **kwargs):
    """兼容新版 Starlette TemplateResponse 签名。"""
    ctx = ctx or {}
    ctx["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=ctx, **kwargs)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/papers/", status_code=303)
    return _tmpl(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return _tmpl(request, "login.html", {"error": "用户名或密码错误"}, status_code=401)
    if not user.is_active:
        return _tmpl(request, "login.html", {"error": "账号已禁用"}, status_code=403)
    user.last_login = datetime.utcnow()
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/papers/", status_code=303)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/papers/", status_code=303)
    return _tmpl(request, "login.html", {"error": None, "mode": "register"})


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if len(username) < 2 or len(username) > 32:
        return _tmpl(request, "login.html", {"error": "用户名长度需在 2-32 之间", "mode": "register"}, status_code=400)
    if len(password) < 6:
        return _tmpl(request, "login.html", {"error": "密码至少 6 位", "mode": "register"}, status_code=400)
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return _tmpl(request, "login.html", {"error": "用户名已存在", "mode": "register"}, status_code=400)

    is_first = db.query(User).count() == 0
    user = User(username=username, hashed_password=hash_password(password), is_admin=is_first)
    db.add(user)
    db.flush()

    from src.scraper import DEFAULT_CATEGORIES
    from src.filter import HIGH_SIGNAL_KEYWORDS, NOTABLE_AUTHORS

    _DEFAULT_INTEREST_TABLE = [
        {"name": "LLM", "description": "Large language model training, alignment, RLHF, reasoning, scaling, and inference optimization."},
        {"name": "Agent", "description": "LLM-based agents, tool use, multi-agent systems, agentic workflows, and test-time compute scaling."},
    ]
    _DEFAULT_KEYWORDS = ["LLM", "Agent", "Reinforcement Learning"]

    config = UserConfig(
        user_id=user.id,
        keywords_json=json.dumps(_DEFAULT_KEYWORDS, ensure_ascii=False),
        categories_json=json.dumps(DEFAULT_CATEGORIES, ensure_ascii=False),
        interests_text="",
        interest_table_json=json.dumps(_DEFAULT_INTEREST_TABLE, ensure_ascii=False),
        high_signal_keywords_json=json.dumps(HIGH_SIGNAL_KEYWORDS, ensure_ascii=False),
        low_signal_keywords_json=json.dumps([], ensure_ascii=False),
        notable_authors_json=json.dumps(list(NOTABLE_AUTHORS), ensure_ascii=False),
    )
    db.add(config)
    db.commit()

    request.session["user_id"] = user.id
    return RedirectResponse("/papers/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=303)
