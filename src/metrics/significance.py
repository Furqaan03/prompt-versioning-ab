"""Statistical significance testing between two experiment variants."""
from __future__ import annotations

import numpy as np
from pydantic import BaseModel
from scipy import stats
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import MetricEvent


class VariantStats(BaseModel):
    variant_version_id: str
    n: int
    mean: float
    std: float


class SignificanceResult(BaseModel):
    variant_a: VariantStats
    variant_b: VariantStats
    p_value: float
    is_significant: bool
    confidence_level: float
    winner_variant_id: str | None
    test_used: str


def _get_values(session: Session, experiment_id: str, variant_version_id: str, metric_name: str) -> np.ndarray:
    rows = session.scalars(
        select(MetricEvent.value).where(
            MetricEvent.experiment_id == experiment_id,
            MetricEvent.variant_version_id == variant_version_id,
            MetricEvent.metric_name == metric_name,
            MetricEvent.is_error == False,  # noqa: E712
        )
    ).all()
    return np.array(rows, dtype=float)


def compare_variants(
    session: Session,
    experiment_id: str,
    variant_a_id: str,
    variant_b_id: str,
    metric_name: str,
    confidence_level: float = 0.95,
) -> SignificanceResult:
    a_values = _get_values(session, experiment_id, variant_a_id, metric_name)
    b_values = _get_values(session, experiment_id, variant_b_id, metric_name)

    a_stats = VariantStats(
        variant_version_id=variant_a_id, n=len(a_values),
        mean=float(np.mean(a_values)) if len(a_values) else 0.0,
        std=float(np.std(a_values, ddof=1)) if len(a_values) > 1 else 0.0,
    )
    b_stats = VariantStats(
        variant_version_id=variant_b_id, n=len(b_values),
        mean=float(np.mean(b_values)) if len(b_values) else 0.0,
        std=float(np.std(b_values, ddof=1)) if len(b_values) > 1 else 0.0,
    )

    if len(a_values) < 2 or len(b_values) < 2:
        return SignificanceResult(
            variant_a=a_stats, variant_b=b_stats, p_value=1.0, is_significant=False,
            confidence_level=confidence_level, winner_variant_id=None, test_used="insufficient_data",
        )

    # Use Mann-Whitney U (non-parametric) — doesn't assume normality, which
    # latency/quality-score distributions rarely satisfy in practice.
    statistic, p_value = stats.mannwhitneyu(a_values, b_values, alternative="two-sided")

    is_significant = p_value < (1 - confidence_level)
    winner_id = None
    if is_significant:
        winner_id = variant_a_id if a_stats.mean > b_stats.mean else variant_b_id

    return SignificanceResult(
        variant_a=a_stats, variant_b=b_stats, p_value=float(p_value),
        is_significant=is_significant, confidence_level=confidence_level,
        winner_variant_id=winner_id, test_used="mann_whitney_u",
    )
