# Pitch scripts and follow-up questions

Say these out loud; do not read them. The framing in every version is the same and is true: **a portfolio project, built as a reference implementation for a small finance office use case. No real client.**

## The 2-minute pitch

> I built a production-grade RAG system as a reference implementation for a realistic use case: a small finance office, like a bookkeeping firm, where staff need fast answers from internal policies. Things like "who approves a 20,000 payment" or "a supplier emailed new bank details, what do I do". There was no real client. I developed and measured it on a public documentation corpus, and I added a synthetic finance-office corpus to show how it maps.
>
> In that domain a wrong answer is worse than no answer, so I started with the ruler, not the model. I wrote a golden set of 53 questions, six of them deliberately unanswerable, and fixed a quality bar before the first run: at most 5% unfaithful claims, every unanswerable question refused, at least 80% correct.
>
> Then I let the numbers decide. Hybrid search, the usual advice, did not help. A reranker on 30 candidates broke questions; on 10 it raised hit@5 from 0.905 to 0.952 and broke nothing. For the model, Haiku failed the bar, Opus passed at the edge, and Sonnet passed with 90.5% correct and 0% unfaithful at about 0.7 cents a question, so I chose Sonnet. Free local models did not come close.
>
> Then production: API keys, rate limiting, a daily dollar budget, a cache, one trace line per question, alerts on errors, latency and budget, deployed on Cloud Run with keyless CD. The best story is a bug that only existed in the cloud: the free database went to sleep and every question started failing. I reproduced it on purpose before fixing it.
>
> What I would do next for a real finance office is access control per document, an audit log, and running the evals on the firm's own documents.

## The 5-minute pitch

Use this when they say "walk me through the project". Each part is about a minute.

**1. Framing and problem (about 45 seconds)**

> This is a portfolio project. I designed it around a small finance office, a 10 to 20 person bookkeeping firm, as the target user, because it is a realistic case where RAG fits and where mistakes are expensive. There was no real client, and I want to be clear about that. I built and measured everything on the FastAPI documentation, because a public corpus can be versioned and evaluated openly, and I wrote a synthetic finance corpus to map it onto that domain.
>
> The requirements I designed for: answer only from the firm's documents, cite the exact section, refuse when the documents don't say, keep costs bounded, and keep client data out of logs.

**2. Architecture (about 45 seconds)**

> Offline, documents are chunked by Markdown headings, so a section and its table stay together, embedded locally so no document text goes to an embeddings API, and stored in Postgres with pgvector. One database instead of a vector database plus a relational one, because 745 chunks don't justify two systems.
>
> Online, a question passes an API key and rate limit, then the cache, then the daily budget. Then vector search for 10 candidates, a cross-encoder reranks to 5, and Claude answers only from those 5, with numbered citations, or with one exact refusal sentence.

**3. How I chose each component (about 90 seconds)**

> I built the golden set and two evals before optimizing anything. The retrieval eval is cheap and deterministic: hit@5, recall@5, MRR. The answer eval uses a stronger model as a judge, and marks any claim that is not in the sources as unfaithful, even if it's true. All models get the same sources, so I compare models, not searches.
>
> Results: hybrid search didn't move hit@5. Reranking 30 candidates broke 4 questions; reranking 10 fixed 2 and broke none. Query rewriting looked like a win in one run and was noise in the next, which taught me to run anything with an LLM in it more than once. For the model, Sonnet was the cheapest that passed the bar I set in advance.
>
> One finding I use a lot: an unanswerable question had a higher similarity score than an answerable one, 0.765 vs 0.729. So you can't use a similarity threshold to decide whether to answer. Refusal is the model's job, and the eval checks it.

**4. Production and the bug story (about 90 seconds)**

> For cost: every response reports its cost, there's a daily budget that returns 503, and an exact-match cache. Not a semantic cache, because "make it optional" and "make it required" embed close together and have opposite answers.
>
> For security: API keys, no secrets in code, prompt-injection defenses, and the model has no tools, so a successful injection can at most produce a wrong answer. A small red-team eval runs as a regression check.
>
> For operations: separate liveness and readiness, alerts on errors, p95 latency and budget, and CD from GitHub with Workload Identity Federation, deploying a no-traffic revision, smoke-testing it, then shifting traffic.
>
> The bug: after deploying, everything worked, and after five idle minutes every question returned 500. The serverless database suspends and closes connections, and my service held one stale connection. It never happened locally. I reproduced it on purpose by waiting, then added a reconnect that retries once, only on connection errors and only for read queries, with a thread-safety test. Then I waited over 9 minutes again and confirmed it.

**5. Limits and next steps (about 45 seconds)**

> What it doesn't have: real users, so my numbers come from a 53-question set. The judge is only lightly calibrated; I have the labeling tooling but haven't finished the agreement measurement. State is per instance. For a real finance office I'd add per-document access control inside the SQL query, an audit log of who asked what and which sections they saw, PII redaction at ingest, SSO, and I'd build the golden set with the firm's own staff. I'd also re-test hybrid search there, because client codes and account numbers are exactly what keyword search is good at.

## Likely follow-up questions

**"So who was the client?"**
There wasn't one. I designed it around a small finance office scenario as a reference implementation, and I developed it on a public corpus so I could measure it openly. The synthetic finance documents in the repo are clearly marked as fictional.

**"Why not build it on real finance documents?"**
I don't have a firm's documents, and I wouldn't use real client data in a public repo. A public, versioned corpus let me publish the golden set and every result. The synthetic corpus shows the mapping; the honest gap is that I haven't run the evals on it yet.

**"How do you know the answers are right?"**
A 53-question golden set, six unanswerable. A retrieval eval for search and an LLM judge for answers, with the bar fixed before the first run. Sonnet: 90.5% correct, 0% unfaithful. The weakness: I checked only 3 judge verdicts by hand, and agreed with 2.

**"How would you stop staff from seeing documents they shouldn't?"**
An access label per document, and the filter goes inside the SQL query before ranking, so restricted text never reaches the model. Never filter after generation. The cache key must include the user's labels too. And a test that a bookkeeper's question cannot retrieve a partners-only section. This part is design, not built.

**"What about client data and PII?"**
Embeddings run locally, so documents don't go to an embeddings API. Only the 5 retrieved sections and the question go to the LLM. The question text is not in operational logs. For a firm I'd add PII redaction at ingest with a human review, and check the provider's data-retention terms and region before go-live.

**"Why should a finance office trust an LLM at all?"**
It shouldn't trust it blindly, which is why every claim has a citation to the section, the model refuses when the documents don't answer, and the refusal is measured. The assistant answers "what is our rule", not "what should my client do". Advisory questions are in the golden set as must-refuse.

**"What does it cost?"**
About 0.7 cents per question on Sonnet, measured from token usage. 15 staff at 10 questions a day is roughly $1 a day before the cache. That's an estimate from per-question cost, not a real bill. A daily budget caps it.

**"Why didn't hybrid search help? Isn't it best practice?"**
On natural-language questions over prose, vectors already found what keywords would. It's still in the code as an opt-in mode. On finance documents with client codes and account numbers I'd expect a different result, and the synthetic golden set has questions designed to test that.

**"What would break with 100 firms using it?"**
In order: the instance cap, then per-instance state (budget, cache and rate limit would multiply by the number of instances, so move them to Redis), then the single database connection per instance (move to a pool). Plus per-tenant isolation, which is a bigger change than scaling.

**"What would you do differently?"**
Build the golden set on day one, which I did, and I'd do it again. Add API-layer tests from the start: a Docker healthcheck caught a crash the tests missed. Run the same Postgres version everywhere: the cloud database came up as 18 while local and CI were 16.
