# Prompt Versioning & A/B Testing Platform

Treats prompts as versioned artifacts, like code. Deploy multiple prompt
variants simultaneously, split traffic between them with consistent hashing,
measure performance with proper statistical significance testing, and
auto-detect a winner — bringing feature-flagging rigor to LLM prompt changes
instead of editing a string in production and hoping.

## Why this exists

Most teams change prompts by hand-editing production and watching for
complaints. This is the missing experimentation layer: prompts get versions,
diffs, rollback, and A/B tests with real p-values instead of vibes.

## Architecture

```
src/models.py                  SQLAlchemy schema: Prompt, PromptVersion, Experiment,
                                VariantAssignment, MetricEvent, AuditLogEntry
src/registry.py                versioning, activation/rollback, unified diffs,
                                {{variable}} template rendering
src/experiment/splitter.py     consistent-hash traffic split — same user_key always
                                gets the same variant
src/experiment/guardrails.py   auto-stops an experiment if any variant's error rate
                                exceeds its configured threshold
src/experiment/serving.py      resolves active version or running-experiment variant,
                                renders the template, calls the LLM, logs metrics
src/metrics/significance.py    Mann-Whitney U test between two variants (non-parametric —
                                doesn't assume normally distributed latency/quality scores)
src/api/main.py                FastAPI: prompt CRUD, experiment lifecycle, /v1/serve,
                                /experiments/{id}/results
```

## Design decisions

- **SQLite by default, Postgres via docker-compose.** The schema is plain
  SQLAlchemy with no SQLite-specific types, so `DATABASE_URL` alone switches
  backends — zero-infra for local dev, Postgres for anything resembling
  production concurrency.
- **Traffic splitting uses SHA-256 of `{experiment_id}:{user_key}`, not random.choice().**
  A user must see the same variant on every request for the length of an
  experiment, or the comparison is meaningless. Consistent hashing guarantees
  that without storing a lookup table per user.
- **Mann-Whitney U over a t-test.** Latency and LLM-judge quality scores are
  rarely normally distributed (heavy right tail on latency, bounded/discrete
  on 1-5 quality scores). A non-parametric test avoids a false-confidence
  p-value from violating the t-test's normality assumption.
- **Only one version can be "active" per prompt at a time.** Rollback is
  re-activating an older version — an audit-logged, no-deploy operation, not
  a separate rollback code path.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env      # fill in OPENAI_API_KEY
uvicorn src.api.main:app --reload
```

## Example flow

```bash
# 1. Create a prompt and two variants
curl -X POST localhost:8000/prompts -d '{"name": "subject-line-writer"}' -H "Content-Type: application/json"
curl -X POST localhost:8000/prompts/<id>/versions -d '{"template": "Write a subject line for: {{topic}}", "commit_message": "zero-shot baseline", "activate": true}' -H "Content-Type: application/json"
curl -X POST localhost:8000/prompts/<id>/versions -d '{"template": "Think step by step, then write a punchy subject line for: {{topic}}", "commit_message": "chain-of-thought variant"}' -H "Content-Type: application/json"

# 2. Launch a 50/50 experiment between the two versions
curl -X POST localhost:8000/experiments -d '{"name": "cot-vs-baseline", "prompt_id": "<id>", "variant_version_ids": ["<v1-id>", "<v2-id>"], "traffic_split": [0.5, 0.5]}' -H "Content-Type: application/json"
curl -X POST localhost:8000/experiments/<exp-id>/start

# 3. Traffic through /v1/serve gets split automatically
curl -X POST localhost:8000/v1/serve -d '{"prompt_id": "<id>", "variables": {"topic": "flash sale"}, "user_key": "user-42"}' -H "Content-Type: application/json"

# 4. Check significance once enough samples accumulate
curl localhost:8000/experiments/<exp-id>/results
```

## Tests

```bash
pytest tests/ -v
```

11 tests covering version increment/activation/rollback, template rendering,
consistent-hash split stability and distribution, and significance testing
(no-difference case, clear-winner case, insufficient-data case) — all run
fully offline against an in-memory SQLite DB, no API key required.

## Docker

```bash
docker compose up --build   # runs Postgres + the API
```

## Status

Phases 1-3 complete (registry, experiment engine + guardrails, significance
testing) plus a working serving endpoint. Phase 4's dedicated management UI
and Phase 5's seeded demo scenario are not built — the FastAPI `/docs` page
serves as the management interface for now.
