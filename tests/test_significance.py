import numpy as np

from src.metrics.significance import compare_variants
from src.models import MetricEvent


def _seed_metric(session, experiment_id, variant_id, values):
    for v in values:
        session.add(MetricEvent(experiment_id=experiment_id, variant_version_id=variant_id, metric_name="quality_score", value=v))
    session.commit()


def test_identical_distributions_are_not_significant(session):
    rng = np.random.default_rng(42)
    values_a = rng.normal(5, 1, 100).tolist()
    values_b = rng.normal(5, 1, 100).tolist()
    _seed_metric(session, "exp-1", "v-a", values_a)
    _seed_metric(session, "exp-1", "v-b", values_b)

    result = compare_variants(session, "exp-1", "v-a", "v-b", "quality_score")
    assert result.is_significant is False


def test_clearly_different_distributions_are_significant(session):
    rng = np.random.default_rng(42)
    values_a = rng.normal(3, 0.5, 100).tolist()
    values_b = rng.normal(8, 0.5, 100).tolist()
    _seed_metric(session, "exp-1", "v-a", values_a)
    _seed_metric(session, "exp-1", "v-b", values_b)

    result = compare_variants(session, "exp-1", "v-a", "v-b", "quality_score")
    assert result.is_significant is True
    assert result.winner_variant_id == "v-b"


def test_insufficient_data_returns_not_significant(session):
    _seed_metric(session, "exp-1", "v-a", [5.0])
    _seed_metric(session, "exp-1", "v-b", [6.0])
    result = compare_variants(session, "exp-1", "v-a", "v-b", "quality_score")
    assert result.test_used == "insufficient_data"
    assert result.is_significant is False
