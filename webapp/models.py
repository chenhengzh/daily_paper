from datetime import datetime, date
from sqlalchemy import (
    Integer, String, Boolean, Float, Text, DateTime, Date,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from webapp.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    user_type: Mapped[str] = mapped_column(String(16), default="external", nullable=False)  # internal | external
    used_invite_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    config: Mapped["UserConfig"] = relationship("UserConfig", back_populates="user", uselist=False, cascade="all, delete-orphan")
    daily_jobs: Mapped[list["DailyJob"]] = relationship("DailyJob", back_populates="user", cascade="all, delete-orphan")
    paper_results: Mapped[list["UserPaperResult"]] = relationship("UserPaperResult", back_populates="user", cascade="all, delete-orphan")
    chat_messages: Mapped[list["ChatMessage"]] = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")


class UserConfig(Base):
    __tablename__ = "user_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    keywords_json: Mapped[str] = mapped_column(Text, default='["LLM","Agent","Reinforcement Learning","World Model"]')
    categories_json: Mapped[str] = mapped_column(Text, default='["cs.AI","cs.LG","cs.CL","stat.ML","cs.RO","cs.MA","cs.NE"]')
    interests_text: Mapped[str] = mapped_column(Text, default="")
    interest_table_json: Mapped[str] = mapped_column(Text, default="[]")
    high_signal_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    low_signal_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    deemphasized_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    notable_authors_json: Mapped[str] = mapped_column(Text, default="[]")

    llm_api_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    llm_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    max_results: Mapped[int] = mapped_column(Integer, default=800)
    high_priority_target: Mapped[int] = mapped_column(Integer, default=15)
    auto_trigger: Mapped[bool] = mapped_column(Boolean, default=False)
    trigger_hour: Mapped[int] = mapped_column(Integer, default=18)
    trigger_minute: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="config")


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arxiv_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    abs_url: Mapped[str] = mapped_column(String(512), default="")
    pdf_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    categories_json: Mapped[str] = mapped_column(Text, default="[]")
    authors_json: Mapped[str] = mapped_column(Text, default="[]")
    paper_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    results: Mapped[list["UserPaperResult"]] = relationship("UserPaperResult", back_populates="paper", cascade="all, delete-orphan")
    chat_messages: Mapped[list["ChatMessage"]] = relationship("ChatMessage", back_populates="paper", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_papers_paper_date_arxiv_id", "paper_date", "arxiv_id"),
    )


class DailyJob(Base):
    __tablename__ = "daily_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    job_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|scraping|rating|done|failed
    scrape_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rated_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kept_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    high_priority_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_summary_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    daily_ideas_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="daily_jobs")
    paper_results: Mapped[list["UserPaperResult"]] = relationship("UserPaperResult", back_populates="job")

    __table_args__ = (
        UniqueConstraint("user_id", "job_date", name="uq_daily_jobs_user_date"),
    )


class UserPaperResult(Base):
    __tablename__ = "user_paper_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("papers.id"), nullable=False)
    job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("daily_jobs.id"), nullable=True)

    keep: Mapped[bool] = mapped_column(Boolean, default=True)
    keep_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    interest_field: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interest_subfield: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interest_match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tldr: Mapped[str | None] = mapped_column(Text, nullable=True)
    tldr_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")

    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    novelty_claim_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    clarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    potential_impact_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    tier: Mapped[str | None] = mapped_column(String(4), nullable=True)
    high_priority: Mapped[bool] = mapped_column(Boolean, default=False)
    high_priority_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    signal_high_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    signal_notable_authors_json: Mapped[str] = mapped_column(Text, default="[]")
    signal_low_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    signal_evidence_keywords_json: Mapped[str] = mapped_column(Text, default="[]")

    is_bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    bookmarked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="paper_results")
    paper: Mapped["Paper"] = relationship("Paper", back_populates="results")
    job: Mapped["DailyJob"] = relationship("DailyJob", back_populates="paper_results")

    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", name="uq_user_paper"),
        Index("ix_user_paper_results_user_date", "user_id"),
    )


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    code_type: Mapped[str] = mapped_column(String(16), default="internal", nullable=False)  # internal | external
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    used_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("papers.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="chat_messages")
    paper: Mapped["Paper"] = relationship("Paper", back_populates="chat_messages")

    __table_args__ = (
        Index("ix_chat_messages_user_paper", "user_id", "paper_id"),
    )
