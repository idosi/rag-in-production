# Portfolio wording

Ready-to-paste text. Every version says the same true thing: a portfolio project, designed as a reference implementation for a small finance office use case, measured on a public corpus. No client names, users or business results.

## README section

> ### Case study: a policy assistant for a small finance office
>
> This repo is a reference implementation of a production-grade RAG assistant, designed around a realistic scenario: a small bookkeeping firm whose staff need cited answers from internal policies (record retention, payment approvals, client onboarding, VAT preparation). It is a portfolio project with no real client. It was built and measured on the FastAPI documentation, and a synthetic finance-office corpus with a 22-question golden set shows how it maps onto that domain.
>
> - [Case study](docs/case-study/case-study.md): problem, architecture, decisions with measured numbers, failures, next steps
> - [Finance-office mapping](docs/case-study/finance-office-mapping.md): sources, confidentiality, PII, refusal, citations, audit trail, access control; what is built and what is design
> - [Synthetic demo corpus](examples/finance-office/): 8 fictional policies and a golden set

## CV bullets

Pick 3 or 4.

- Built a production-grade RAG service (Python, FastAPI, Postgres + pgvector, Claude) as a reference implementation for a small finance office policy assistant; deployed on Cloud Run with Neon, CI/CD via GitHub Actions and Workload Identity Federation.
- Designed a 53-question golden set and two evals (retrieval and LLM-as-judge) with a quality bar fixed in advance; used them to choose a cross-encoder reranker (hit@5 0.905 to 0.952, no regressions) and the cheapest passing model (90.5% correct, 0% unfaithful, about $0.007 per question).
- Measured and rejected popular options with data: hybrid search (no gain), query rewriting (gain was run-to-run noise), and free local models (best: 32% correct, 48% unfaithful).
- Added cost and abuse controls: per-response cost, daily dollar budget, exact-match cache, API keys and rate limiting, prompt-injection defenses with a red-team regression eval.
- Diagnosed a cloud-only outage (serverless Postgres suspending idle connections), reproduced it on purpose, fixed it with a thread-safe reconnect-and-retry-once, and verified it in production; added alerts on errors, p95 latency and budget.

## LinkedIn "Projects" entry

**RAG in production: policy assistant reference implementation**

A portfolio project: a RAG assistant designed for a small finance office scenario, where staff ask questions about internal policies and every answer must cite its source or refuse. Built end to end and measured on a public documentation corpus: golden set and LLM-as-judge evals, reranking chosen by data, model chosen as the cheapest that passes a pre-set bar, daily cost budget, alerts, and keyless CD to Cloud Run. Includes a synthetic finance-office corpus to show the domain mapping. Code and every result are public.

## One-liner (intro call, cover letter)

> I built a production-grade RAG system as a reference implementation for a small finance office use case, and every design decision in it is backed by an eval I wrote.
