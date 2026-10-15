"""Model readiness: pull the model if missing, warm it up, and gate requests until both succeed (FR-003)."""

import asyncio
import logging
import os
from dataclasses import dataclass

from fastapi import HTTPException
from ollama import AsyncClient, ResponseError

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
# Every call to the model must pass these options: a different num_ctx makes Ollama
# reload the model, so the first real request would pay the cold start again.
MODEL_OPTIONS = {"num_ctx": 4096}
KEEP_ALIVE = (
    -1
)  # keep the model loaded; matches OLLAMA_KEEP_ALIVE on the ollama service

RETRY_AFTER_SECONDS = 10
MAX_BACKOFF_SECONDS = 30

logger = logging.getLogger(__name__)


@dataclass
class Readiness:
    status: str = "starting"  # starting | ready
    stage: str = "pulling"  # pulling | warming (meaningful while starting)
    last_error: str | None = (
        None  # warm-up never handles user data, so this is safe to expose
    )


state = Readiness()


async def warm_up(client: AsyncClient) -> None:
    """Retry pull and warm-up until the model answers, then mark the service ready."""
    delay = 2
    while True:
        try:
            state.stage = "pulling"
            try:
                await client.show(MODEL)
            except ResponseError as e:
                if e.status_code != 404:
                    raise
                logger.info("Model %s not present, pulling", MODEL)
                await client.pull(MODEL)
            state.stage = "warming"
            await client.chat(
                MODEL,
                messages=[{"role": "user", "content": "ping"}],
                options={**MODEL_OPTIONS, "num_predict": 1},
                keep_alive=KEEP_ALIVE,
            )
        # Any failure must lead to a retry: an escaped exception would end this background
        # task silently and leave /health "starting" forever.
        except Exception as e:  # noqa: BLE001
            state.last_error = f"{type(e).__name__}: {e}"[:300]
            logger.warning(
                "Warm-up failed at stage %s (%s); retrying in %ss",
                state.stage,
                state.last_error,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_BACKOFF_SECONDS)
        else:
            state.status = "ready"
            state.last_error = None
            logger.info("Model %s loaded and warmed up; ready", MODEL)
            return


def require_ready() -> None:
    """FastAPI dependency: answer 503 "not ready" until the model is pulled and warmed up."""
    if state.status != "ready":
        raise HTTPException(
            status_code=503,
            detail={
                "status": state.status,
                "stage": state.stage,
                "last_error": state.last_error,
            },
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )
