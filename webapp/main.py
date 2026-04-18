import os
import logging
import secrets
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Auto-load .env from project root (does not override existing env vars)
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            if _k.strip() not in os.environ:
                os.environ[_k.strip()] = _v.strip()

_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_handler = RotatingFileHandler(
    _LOG_DIR / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.root.addHandler(_handler)
logging.root.setLevel(logging.INFO)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from webapp.database import init_db
from webapp.services.scheduler import start_scheduler, stop_scheduler
from webapp.routers import auth as auth_router
from webapp.routers import papers as papers_router
from webapp.routers import config as config_router
from webapp.routers import admin as admin_router
from webapp.routers import logs as logs_router

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Daily Paper", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="dp_session",
    max_age=60 * 60 * 24 * 30,  # 30 天
    https_only=False,
)

static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(papers_router.router, prefix="/papers", tags=["papers"])
app.include_router(config_router.router, prefix="/config", tags=["config"])
app.include_router(admin_router.router, prefix="/admin", tags=["admin"])
app.include_router(logs_router.router, prefix="/logs", tags=["logs"])


from fastapi.responses import RedirectResponse

@app.get("/")
async def root():
    return RedirectResponse("/papers/", status_code=302)
