"""Consistent-hashing traffic splitter: same user_key always lands on the same variant."""
from __future__ import annotations

import hashlib

from src.models import Experiment


def assign_variant(experiment: Experiment, user_key: str) -> str:
    """Deterministically maps user_key -> one of experiment.variant_version_ids,
    weighted by experiment.traffic_split. Same user_key always returns the same
    variant for a given experiment (stable across repeated calls)."""
    digest = hashlib.sha256(f"{experiment.id}:{user_key}".encode()).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF  # -> float in [0, 1)

    cumulative = 0.0
    for variant_id, weight in zip(experiment.variant_version_ids, experiment.traffic_split):
        cumulative += weight
        if bucket < cumulative:
            return variant_id
    return experiment.variant_version_ids[-1]  # floating point edge case fallback
