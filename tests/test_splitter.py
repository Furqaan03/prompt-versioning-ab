from src.experiment.splitter import assign_variant
from src.models import Experiment


def _experiment() -> Experiment:
    e = Experiment(
        id="exp-1", name="test", prompt_id="p-1",
        variant_version_ids=["v-a", "v-b"], traffic_split=[0.5, 0.5],
    )
    return e


def test_same_user_always_gets_same_variant():
    experiment = _experiment()
    first = assign_variant(experiment, "user-123")
    for _ in range(20):
        assert assign_variant(experiment, "user-123") == first


def test_distribution_is_roughly_balanced():
    experiment = _experiment()
    assignments = [assign_variant(experiment, f"user-{i}") for i in range(2000)]
    a_count = assignments.count("v-a")
    b_count = assignments.count("v-b")
    # With 2000 samples and a real hash, expect close to 50/50 — allow generous slack.
    assert 800 < a_count < 1200
    assert 800 < b_count < 1200


def test_weighted_split_skews_correctly():
    e = Experiment(id="exp-2", name="t", prompt_id="p-1", variant_version_ids=["v-a", "v-b"], traffic_split=[0.9, 0.1])
    assignments = [assign_variant(e, f"user-{i}") for i in range(2000)]
    a_count = assignments.count("v-a")
    assert a_count > 1600  # should be roughly 90%
