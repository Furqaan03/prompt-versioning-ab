"""Serving layer: resolves active version or experiment variant, fills the template,
calls the LLM, logs metrics. The caller doesn't know or care about the experiment."""
from __future__ import annotations

import time

from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.experiment.guardrails import check_error_rate_guardrail
from src.experiment.splitter import assign_variant
from src.models import Experiment, MetricEvent, PromptVersion, VariantAssignment
from src.registry import get_active_version, render_template

_client: OpenAI | None = None


def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


class ServeResult(BaseModel):
    output_text: str
    variant_version_id: str
    version_number: int
    latency_ms: float
    error: str | None = None


def _get_active_experiment(session: Session, prompt_id: str) -> Experiment | None:
    return session.scalars(
        select(Experiment).where(Experiment.prompt_id == prompt_id, Experiment.status == "running")
    ).first()


def serve(session: Session, prompt_id: str, variables: dict[str, str], user_key: str) -> ServeResult:
    experiment = _get_active_experiment(session, prompt_id)

    if experiment is not None:
        variant_version_id = assign_variant(experiment, user_key)
        session.add(VariantAssignment(experiment_id=experiment.id, user_key=user_key, variant_version_id=variant_version_id))
        session.commit()
        version = session.get(PromptVersion, variant_version_id)
    else:
        version = get_active_version(session, prompt_id)

    if version is None:
        raise ValueError(f"No active version (and no running experiment) for prompt {prompt_id}")

    rendered = render_template(version.template, variables)

    start = time.perf_counter()
    error: str | None = None
    try:
        response = _openai().chat.completions.create(
            model=version.model,
            messages=[{"role": "user", "content": rendered}],
            temperature=version.temperature,
            max_tokens=version.max_tokens,
        )
        output_text = response.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001 — logged as a metric event, not swallowed silently
        output_text = ""
        error = str(exc)
    latency_ms = (time.perf_counter() - start) * 1000

    if experiment is not None:
        session.add(MetricEvent(
            experiment_id=experiment.id, variant_version_id=version.id,
            metric_name="latency_ms", value=latency_ms, is_error=error is not None,
        ))
        session.commit()
        check_error_rate_guardrail(session, experiment)

    return ServeResult(
        output_text=output_text,
        variant_version_id=version.id,
        version_number=version.version_number,
        latency_ms=latency_ms,
        error=error,
    )
