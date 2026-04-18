import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from webapp.database import get_db
from webapp.models import User, UserConfig, InviteCode
from webapp.auth import get_current_user

router = APIRouter()

_TMPL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=_TMPL_DIR)


def _tmpl(request, name, ctx=None, **kwargs):
    ctx = ctx or {}
    ctx["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=ctx, **kwargs)


def _require_admin(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


@router.get("", response_class=HTMLResponse)
async def admin_redirect():
    return RedirectResponse("/admin/", status_code=301)


@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request, db: Session = Depends(get_db)):
    user = _require_admin(request, db)
    return _tmpl(request, "admin.html", {"user": user})


@router.get("/users", response_class=JSONResponse)
async def list_users(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    users = db.query(User).order_by(User.id).all()
    result = []
    for u in users:
        result.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "user_type": u.user_type,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
        })
    return result


def _is_superadmin(user: User) -> bool:
    return user.username == "admin"


@router.put("/users/{user_id}", response_class=JSONResponse)
async def update_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    body = await request.json()
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 编辑管理员账号需要超级管理员权限
    if target.is_admin and not _is_superadmin(admin):
        raise HTTPException(status_code=403, detail="只有超级管理员可以编辑管理员账号")
    if "user_type" in body:
        if body["user_type"] not in ("internal", "external"):
            raise HTTPException(status_code=400, detail="用户类型只能是 internal 或 external")
        target.user_type = body["user_type"]
    if "is_active" in body:
        if target.id == admin.id and not body["is_active"]:
            raise HTTPException(status_code=400, detail="不能禁用自己的账号")
        target.is_active = bool(body["is_active"])
    if "is_admin" in body:
        if not _is_superadmin(admin):
            raise HTTPException(status_code=403, detail="只有超级管理员可以修改管理员权限")
        if target.id == admin.id and not body["is_admin"]:
            raise HTTPException(status_code=400, detail="不能撤销自己的管理员权限")
        target.is_admin = bool(body["is_admin"])
    db.commit()
    return {"ok": True}


@router.get("/invite-codes", response_class=JSONResponse)
async def list_invite_codes(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    codes = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
    return [
        {
            "code": c.code,
            "code_type": c.code_type,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in codes
    ]


@router.post("/invite-codes", response_class=JSONResponse)
async def create_invite_codes(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    body = await request.json()
    count = max(1, min(50, int(body.get("count", 1))))
    code_type = body.get("code_type", "external")
    if code_type not in ("internal", "external"):
        code_type = "external"
    created = []
    for _ in range(count):
        code = list(secrets.token_urlsafe(16))
        # 倒数第四位：internal=字母，external=数字
        if code_type == "internal":
            code[-4] = secrets.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
        else:
            code[-4] = secrets.choice("0123456789")
        code = "".join(code)
        db.add(InviteCode(code=code, created_by=admin.id, code_type=code_type))
        created.append(code)
    db.commit()
    return {"codes": created}


@router.delete("/invite-codes/{code}", response_class=JSONResponse)
async def delete_invite_code(code: str, request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    invite = db.query(InviteCode).filter(InviteCode.code == code).first()
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    db.delete(invite)
    db.commit()
    return {"ok": True}
