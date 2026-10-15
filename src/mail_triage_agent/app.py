import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from ollama import AsyncClient
from pydantic import BaseModel, ConfigDict

from mail_triage_agent import readiness, triage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up in the background so /health can answer "not ready" while the model loads.
    task = asyncio.create_task(
        readiness.warm_up(AsyncClient(host=readiness.OLLAMA_HOST))
    )
    yield
    task.cancel()


app = FastAPI(
    title="Mail Triage Agent",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)


@app.get("/health", dependencies=[Depends(readiness.require_ready)])
def health() -> dict[str, str]:
    """200 once the model is pulled and warmed up; 503 with the current stage before that."""
    return {"status": "ready", "model": readiness.MODEL}


class TriageRequest(BaseModel):
    # Plain strings for now; input validation (FR-002) comes with its own change.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"email": "jan.nowak@example.com", "message": "Nie działa mi komputer"}
            ]
        }
    )

    email: str
    message: str


class TriageResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"department": "help-desk@example.com"}]}
    )

    department: str


# Fixed bodies: errors never echo the request.
ERRORS: dict[type[triage.TriageError], tuple[int, str]] = {
    triage.NoDecision: (
        502,
        "no department decision was produced; no email was sent",
    ),
    triage.SendFailed: (502, "sending the email failed; no email was sent"),
    triage.RoutingTimeout: (504, "the model did not answer in time; no email was sent"),
}


@app.post(
    "/api/v1/triage",
    dependencies=[Depends(readiness.require_ready)],
    responses={
        502: {"description": "No decision, or the send failed; no email was sent"},
        503: {"description": "The model isn't ready yet"},
        504: {"description": "A model call timed out; no email was sent"},
    },
)
def triage_request(request: TriageRequest) -> TriageResponse:
    """Forward the request to the department that owns it; returns where the email went."""
    # Sync def: FastAPI runs it in its threadpool, so the blocking agent call is fine here.
    try:
        department = triage.route(request.email, request.message)
    except triage.TriageError as e:
        status, detail = ERRORS[type(e)]
        raise HTTPException(status_code=status, detail=detail) from None
    return TriageResponse(department=department)
