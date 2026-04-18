import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from webapp.database import init_db
from webapp.services.scheduler import start_scheduler, stop_scheduler
from webapp.routers import auth as auth_router
from webapp.routers import papers as papers_router
from webapp.routers import config as config_router

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


from fastapi.responses import RedirectResponse

@app.get("/")
async def root():
    return RedirectResponse("/papers/", status_code=302)
