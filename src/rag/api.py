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

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from rag.pipeline import RAGPipeline, build_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code before `yield` runs at startup, code after it at shutdown.
    # Loading the embedding model takes seconds; doing it per request would make
    # every question that much slower. app.state is a place to keep shared objects.
    app.state.pipeline = build_pipeline()
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


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request) -> AskResponse:
    # By the time we get here, FastAPI has already parsed and validated the JSON
    # into `body`. An invalid request never reaches this line.
    #
    # A sync endpoint: FastAPI runs it in a thread pool, so the blocking DB and
    # LLM calls do not freeze the event loop.
    pipeline: RAGPipeline = request.app.state.pipeline
    answer = pipeline.ask(body.question)
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
