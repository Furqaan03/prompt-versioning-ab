"""Auto-stop conditions: error-rate spikes and severely underperforming variants."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import AuditLogEntry, Experiment, MetricEvent


def check_error_rate_guardrail(session: Session, experiment: Experiment) -> bool:
    """Returns True and stops the experiment if any variant's error rate exceeds
    the configured threshold."""
    for variant_id in experiment.variant_version_ids:
        events = session.scalars(
            select(MetricEvent).where(
                MetricEvent.experiment_id == experiment.id,
                MetricEvent.variant_version_id == variant_id,
            )
        ).all()
        if not events:
            continue
        error_rate = sum(1 for e in events if e.is_error) / len(events)
        if error_rate > experiment.error_rate_stop_threshold:
            experiment.status = "cancelled"
            session.add(AuditLogEntry(
                action="experiment.auto_stop",
                details=(
                    f"experiment={experiment.id} variant={variant_id} "
                    f"error_rate={error_rate:.1%} exceeded threshold "
                    f"{experiment.error_rate_stop_threshold:.1%}"
                ),
            ))
            session.commit()
            return True
    return False
