"""Prompt registry service: versioning, activation/rollback, diffs, audit trail."""
from __future__ import annotations

import difflib

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import AuditLogEntry, Prompt, PromptVersion


def create_prompt(session: Session, name: str) -> Prompt:
    prompt = Prompt(name=name)
    session.add(prompt)
    session.add(AuditLogEntry(action="prompt.create", details=f"name={name}"))
    session.commit()
    session.refresh(prompt)
    return prompt


def create_version(
    session: Session,
    prompt_id: str,
    template: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    max_tokens: int = 512,
    commit_message: str = "",
    activate: bool = False,
    actor: str = "system",
) -> PromptVersion:
    existing = session.scalars(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt_id)
    ).all()
    next_version_number = max((v.version_number for v in existing), default=0) + 1

    version = PromptVersion(
        prompt_id=prompt_id,
        version_number=next_version_number,
        template=template,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        commit_message=commit_message,
    )
    session.add(version)
    session.add(AuditLogEntry(actor=actor, action="version.create", details=f"prompt_id={prompt_id} v{next_version_number}"))

    if activate:
        session.flush()
        activate_version(session, version.id, actor=actor)

    session.commit()
    session.refresh(version)
    return version


def activate_version(session: Session, version_id: str, actor: str = "system") -> PromptVersion:
    version = session.get(PromptVersion, version_id)
    if version is None:
        raise ValueError(f"No version {version_id}")

    # Deactivate all other versions of this prompt (only one active at a time = current rollback target).
    siblings = session.scalars(
        select(PromptVersion).where(PromptVersion.prompt_id == version.prompt_id)
    ).all()
    for sibling in siblings:
        sibling.is_active = sibling.id == version_id

    session.add(AuditLogEntry(
        actor=actor, action="version.activate",
        details=f"prompt_id={version.prompt_id} version={version.version_number} ({version_id})",
    ))
    session.commit()
    session.refresh(version)
    return version


def rollback_to_version(session: Session, version_id: str, actor: str = "system") -> PromptVersion:
    """Rollback is just re-activating an older version. No deploy required."""
    version = activate_version(session, version_id, actor=actor)
    session.add(AuditLogEntry(actor=actor, action="version.rollback", details=f"rolled back to {version_id}"))
    session.commit()
    return version


def get_active_version(session: Session, prompt_id: str) -> PromptVersion | None:
    return session.scalars(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt_id, PromptVersion.is_active == True)  # noqa: E712
    ).first()


def diff_versions(session: Session, version_id_a: str, version_id_b: str) -> str:
    a = session.get(PromptVersion, version_id_a)
    b = session.get(PromptVersion, version_id_b)
    if a is None or b is None:
        raise ValueError("One or both versions not found")
    diff = difflib.unified_diff(
        a.template.splitlines(), b.template.splitlines(),
        fromfile=f"v{a.version_number}", tofile=f"v{b.version_number}", lineterm="",
    )
    return "\n".join(diff)


def render_template(template: str, variables: dict[str, str]) -> str:
    """Fills {{variable}} placeholders. Raises if any required variable is missing."""
    import re

    required = set(re.findall(r"\{\{(\w+)\}\}", template))
    missing = required - variables.keys()
    if missing:
        raise ValueError(f"Missing template variables: {missing}")

    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered
