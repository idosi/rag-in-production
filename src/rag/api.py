"""HTTP API.

uvicorn rag.api:app --reload    ->  interactive docs at http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from rag.pipeline import RAGPipeline, build_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model and open the DB connection once at startup,
    # not on every request.
    app.state.pipeline = build_pipeline()
    yield
    app.state.pipeline.store.conn.close()


app = FastAPI(title="RAG in production", version="0.1.0", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class Citation(BaseModel):
    id: int
    heading: str
    url: str
    score: float
    cited: bool


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    usage: dict


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request) -> AskResponse:
    # A sync endpoint: FastAPI runs it in a thread pool, so the blocking DB and
    # LLM calls do not freeze the event loop.
    pipeline: RAGPipeline = request.app.state.pipeline
    answer = pipeline.ask(body.question)
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
    count = request.app.state.pipeline.store.count_chunks()
    return {"status": "ok", "chunks": count}
