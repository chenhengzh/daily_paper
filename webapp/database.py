import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(INSTANCE_DIR, 'daily_paper.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from webapp.models import User, UserConfig, Paper, DailyJob, UserPaperResult, InviteCode  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Add columns introduced after initial schema (idempotent)
    with engine.connect() as conn:
        for col_def in [
            "ALTER TABLE user_paper_results ADD COLUMN summary_zh TEXT",
            "ALTER TABLE users ADD COLUMN used_invite_code VARCHAR(32)",
            "ALTER TABLE invite_codes ADD COLUMN code_type VARCHAR(16) NOT NULL DEFAULT 'internal'",
            "ALTER TABLE users ADD COLUMN user_type VARCHAR(16) NOT NULL DEFAULT 'external'",
            "ALTER TABLE user_configs ADD COLUMN auto_trigger BOOLEAN NOT NULL DEFAULT 1",
            "ALTER TABLE user_configs ADD COLUMN trigger_hour INTEGER NOT NULL DEFAULT 9",
            "ALTER TABLE user_configs ADD COLUMN trigger_minute INTEGER NOT NULL DEFAULT 30",
            "ALTER TABLE user_configs ADD COLUMN deemphasized_keywords_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE daily_jobs ADD COLUMN input_tokens INTEGER",
            "ALTER TABLE daily_jobs ADD COLUMN output_tokens INTEGER",
            "ALTER TABLE user_paper_results ADD COLUMN is_bookmarked BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE user_paper_results ADD COLUMN bookmarked_at DATETIME",
        ]:
            try:
                conn.execute(__import__("sqlalchemy").text(col_def))
                conn.commit()
            except Exception:
                pass  # column already exists
