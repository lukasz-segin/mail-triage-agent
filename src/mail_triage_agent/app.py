import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from ollama import AsyncClient

from mail_triage_agent import readiness


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
