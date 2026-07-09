"""FastAPI service: prompt registry CRUD, experiment lifecycle, serving, significance."""
from __future__ import annotations

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db import get_session, init_db
from src.experiment.serving import serve
from src.metrics.significance import compare_variants
from src.models import Experiment, Prompt, PromptVersion
from src.registry import create_prompt, create_version, diff_versions, rollback_to_version

load_dotenv()

app = FastAPI(title="Prompt Versioning & A/B Testing Platform")


def get_db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ---- Prompt registry ----

class CreatePromptRequest(BaseModel):
    name: str


@app.post("/prompts")
def create_prompt_endpoint(req: CreatePromptRequest, session: Session = Depends(get_db)):
    prompt = create_prompt(session, req.name)
    return {"id": prompt.id, "name": prompt.name}


class CreateVersionRequest(BaseModel):
    template: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 512
    commit_message: str = ""
    activate: bool = False


@app.post("/prompts/{prompt_id}/versions")
def create_version_endpoint(prompt_id: str, req: CreateVersionRequest, session: Session = Depends(get_db)):
    version = create_version(session, prompt_id, **req.model_dump())
    return {"id": version.id, "version_number": version.version_number, "is_active": version.is_active}


@app.get("/prompts/{prompt_id}/versions")
def list_versions_endpoint(prompt_id: str, session: Session = Depends(get_db)):
    prompt = session.get(Prompt, prompt_id)
    if prompt is None:
        raise HTTPException(404, "Prompt not found")
    return [
        {"id": v.id, "version_number": v.version_number, "is_active": v.is_active, "commit_message": v.commit_message}
        for v in prompt.versions
    ]


@app.get("/prompts/{prompt_id}/versions/{version_number}")
def get_version_endpoint(prompt_id: str, version_number: int, session: Session = Depends(get_db)):
    version = next((v for v in session.get(Prompt, prompt_id).versions if v.version_number == version_number), None)
    if version is None:
        raise HTTPException(404, "Version not found")
    return {"id": version.id, "template": version.template, "model": version.model}


@app.get("/prompts/{prompt_id}/diff")
def diff_endpoint(prompt_id: str, version_a: str, version_b: str, session: Session = Depends(get_db)):
    return {"diff": diff_versions(session, version_a, version_b)}


class RollbackRequest(BaseModel):
    version_id: str
    actor: str = "api-user"


@app.post("/prompts/{prompt_id}/rollback")
def rollback_endpoint(prompt_id: str, req: RollbackRequest, session: Session = Depends(get_db)):
    version = rollback_to_version(session, req.version_id, actor=req.actor)
    return {"active_version_id": version.id, "version_number": version.version_number}


# ---- Experiments ----

class CreateExperimentRequest(BaseModel):
    name: str
    prompt_id: str
    variant_version_ids: list[str]
    traffic_split: list[float]
    primary_metric: str = "latency_ms"
    target_sample_size: int = 200


@app.post("/experiments")
def create_experiment_endpoint(req: CreateExperimentRequest, session: Session = Depends(get_db)):
    if abs(sum(req.traffic_split) - 1.0) > 1e-6:
        raise HTTPException(400, "traffic_split must sum to 1.0")
    experiment = Experiment(**req.model_dump(), status="draft")
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return {"id": experiment.id, "status": experiment.status}


@app.post("/experiments/{experiment_id}/start")
def start_experiment(experiment_id: str, session: Session = Depends(get_db)):
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    experiment.status = "running"
    session.commit()
    return {"status": "running"}


@app.post("/experiments/{experiment_id}/pause")
def pause_experiment(experiment_id: str, session: Session = Depends(get_db)):
    experiment = session.get(Experiment, experiment_id)
    experiment.status = "cancelled"
    session.commit()
    return {"status": "cancelled"}


@app.get("/experiments/{experiment_id}/results")
def experiment_results(experiment_id: str, session: Session = Depends(get_db)):
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    ids = experiment.variant_version_ids
    if len(ids) != 2:
        raise HTTPException(400, "Results endpoint currently supports 2-variant experiments")
    result = compare_variants(session, experiment_id, ids[0], ids[1], experiment.primary_metric)
    return result.model_dump()


# ---- Serving ----

class ServeRequest(BaseModel):
    prompt_id: str
    variables: dict[str, str] = {}
    user_key: str


@app.post("/v1/serve")
def serve_endpoint(req: ServeRequest, session: Session = Depends(get_db)):
    result = serve(session, req.prompt_id, req.variables, req.user_key)
    return result.model_dump()
