from src.registry import (
    activate_version,
    create_prompt,
    create_version,
    get_active_version,
    render_template,
    rollback_to_version,
)


def test_version_numbers_increment(session):
    prompt = create_prompt(session, "email-classifier")
    v1 = create_version(session, prompt.id, template="Classify: {{email}}")
    v2 = create_version(session, prompt.id, template="Classify carefully: {{email}}")
    assert v1.version_number == 1
    assert v2.version_number == 2


def test_activation_deactivates_siblings(session):
    prompt = create_prompt(session, "email-classifier")
    v1 = create_version(session, prompt.id, template="v1", activate=True)
    v2 = create_version(session, prompt.id, template="v2", activate=True)
    session.refresh(v1)
    assert v1.is_active is False
    assert v2.is_active is True


def test_rollback_reactivates_older_version(session):
    prompt = create_prompt(session, "email-classifier")
    v1 = create_version(session, prompt.id, template="v1", activate=True)
    create_version(session, prompt.id, template="v2", activate=True)

    rollback_to_version(session, v1.id)
    active = get_active_version(session, prompt.id)
    assert active.id == v1.id


def test_render_template_fills_variables():
    result = render_template("Hello {{name}}, your order {{order_id}} shipped.", {"name": "Furqaan", "order_id": "42"})
    assert result == "Hello Furqaan, your order 42 shipped."


def test_render_template_raises_on_missing_variable():
    import pytest

    with pytest.raises(ValueError):
        render_template("Hello {{name}}", {})
