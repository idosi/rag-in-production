"""HTTP API: the way other programs (a website, a chat UI) use the RAG system.

HOW TO RUN
    make api        (same as: uv run uvicorn rag.api:app --reload)
    then open http://localhost:8000/docs to try POST /ask from the browser.

"rag.api:app" tells uvicorn (the web server) to import this module and serve the
`app` object. --reload restarts the server whenever you save a file.

LIFECYCLE
    server starts  -> lifespan(): build the pipeline ONCE (model + DB connection)
    each request   -> ask(): validate the JSON, run pipeline.ask, return JSON
    server stops   -> lifespan(): close the DB connection
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from rag.cache import AnswerCache
from rag.config import get_settings
from rag.guarded import BudgetExceeded, GuardedPipeline
from rag.pipeline import build_pipeline
from rag.security import Guard, RateLimiter, parse_keys
from rag.spend import SpendTracker

log = logging.getLogger("rag.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code before `yield` runs at startup, code after it at shutdown.
    # Loading the embedding model takes seconds; doing it per request would make
    # every question that much slower. app.state is a place to keep shared objects.
    app.state.pipeline = build_pipeline()
    s = get_settings()
    # /ask goes through the wrapper (cache + daily budget + cost); /health and shutdown
    # use the raw pipeline, which owns the DB connection.
    budget = s.daily_budget_usd if s.daily_budget_usd > 0 else float("inf")
    app.state.asker = GuardedPipeline(
        inner=app.state.pipeline,
        cache=AnswerCache(s.answer_cache_max_items, s.answer_cache_ttl_seconds),
        spend=SpendTracker(budget),
        # Everything the answer depends on: change any of it and old answers are not reused.
        version=f"{s.llm_model}|docs-{s.docs_version}|k{s.top_k}|{s.retrieval_mode}",
    )
    keys = parse_keys(s.api_keys.get_secret_value() if s.api_keys else None)
    limiter = RateLimiter(s.rate_limit_per_minute) if s.rate_limit_per_minute > 0 else None
    app.state.guard = Guard(keys, limiter)
    if not keys:
        log.warning("API_KEYS is empty: /ask is OPEN to anyone who can reach it")
    yield
    app.state.pipeline.retriever.store.conn.close()


app = FastAPI(title="RAG in production", version="0.1.0", lifespan=lifespan)


# Pydantic models define the JSON shapes. FastAPI uses them to:
#   - validate incoming JSON (wrong type / too short -> automatic 422 error)
#   - convert the outgoing object to JSON
#   - generate the interactive docs at /docs


class AskRequest(BaseModel):
    """Request body:  {"question": "How do I ..."}"""

    question: str = Field(min_length=3, max_length=1000)


class Citation(BaseModel):
    id: int
    heading: str
    url: str
    score: float
    cited: bool


class AskResponse(BaseModel):
    """Response body:  {"answer": "...", "citations": [...], "usage": {...}}"""

    answer: str
    citations: list[Citation]
    usage: dict


# Declares "this API takes a key in the X-API-Key header". Besides reading the header,
# it adds an Authorize button to /docs, so you can try the protected endpoint there.
# auto_error=False: a missing header gives None and OUR guard answers 401 (one place).
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def check_access(request: Request, x_api_key: str | None = Depends(api_key_header)) -> None:
    """Runs BEFORE the endpoint (Depends below). Raises 401/429 and the endpoint never
    executes, so a rejected request costs no embedding and no LLM call."""
    ip = request.client.host if request.client else "unknown"
    request.app.state.guard.check(x_api_key, ip)


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(check_access)])
def ask(body: AskRequest, request: Request) -> AskResponse:
    # By the time we get here, FastAPI has already parsed and validated the JSON
    # into `body`. An invalid request never reaches this line.
    #
    # A sync endpoint: FastAPI runs it in a thread pool, so the blocking DB and
    # LLM calls do not freeze the event loop.
    asker: GuardedPipeline = request.app.state.asker
    try:
        answer = asker.ask(body.question)
    except BudgetExceeded as e:
        # 503 = "the service can't answer right now", and a cached question still works.
        raise HTTPException(status_code=503, detail=str(e)) from e
    # Convert our internal Answer into the public response shape. Keeping the two
    # separate means we can change internals without breaking API clients.
    return AskResponse(
        answer=answer.text,
        citations=[
            Citation(
                id=i,
                heading=s.chunk.heading,
                url=s.chunk.url,
                score=round(s.score, 4),
                cited=i in answer.cited,
            )
            for i, s in enumerate(answer.sources, start=1)
        ],
        usage=answer.usage,
    )


@app.get("/health")
def health(request: Request) -> dict:
    # Used by load balancers / cloud platforms (step 3) to check the service is
    # alive. It touches the DB, so "ok" means the database is reachable too.
    count = request.app.state.pipeline.retriever.store.count_chunks()
    return {"status": "ok", "chunks": count}
