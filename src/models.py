"""Git-for-prompts schema: prompts, versions, experiments, variant assignments,
metric events, and an audit log."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    versions: Mapped[list["PromptVersion"]] = relationship(back_populates="prompt", order_by="PromptVersion.version_number")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    template: Mapped[str] = mapped_column(Text)  # supports {{variable}} placeholders
    model: Mapped[str] = mapped_column(String, default="gpt-4o-mini")
    temperature: Mapped[float] = mapped_column(Float, default=0.0)
    max_tokens: Mapped[int] = mapped_column(Integer, default=512)
    commit_message: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    prompt: Mapped["Prompt"] = relationship(back_populates="versions")


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"))
    variant_version_ids: Mapped[list] = mapped_column(JSON)  # [prompt_version_id, ...]
    traffic_split: Mapped[list] = mapped_column(JSON)  # [0.5, 0.5] aligned with variant_version_ids
    primary_metric: Mapped[str] = mapped_column(String, default="quality_score")
    target_sample_size: Mapped[int] = mapped_column(Integer, default=200)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft/running/completed/cancelled
    error_rate_stop_threshold: Mapped[float] = mapped_column(Float, default=0.10)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VariantAssignment(Base):
    __tablename__ = "variant_assignments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    user_key: Mapped[str] = mapped_column(String)  # hashed consistently -> same variant every time
    variant_version_id: Mapped[str] = mapped_column(String)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class MetricEvent(Base):
    __tablename__ = "metric_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    variant_version_id: Mapped[str] = mapped_column(String)
    metric_name: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String, default="system")
    action: Mapped[str] = mapped_column(String)
    details: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)
