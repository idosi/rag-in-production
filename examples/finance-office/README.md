# Finance-office demo corpus (synthetic)

A small, **fictional** set of internal documents for a small bookkeeping firm, plus a golden set. It exists to show how the RAG system in this repo maps onto a finance-office use case (see [docs/case-study/finance-office-mapping.md](../../docs/case-study/finance-office-mapping.md)).

**Nothing here is real.** The firm, its policies, amounts and deadlines are invented for a portfolio project. It is not legal, tax or accounting advice, and no real client data was used.

| File | What it is |
|---|---|
| `corpus/*.md` | 8 internal policies and procedures: document retention, client onboarding, expense reimbursement, payment approval, client confidentiality, month-end close, VAT return preparation, remote work security |
| `golden_set.json` | 22 questions in the same format as `evals/golden_set.json`: 18 answerable (direct, paraphrase, code-name, multi) and 4 unanswerable (a live tax rate, a specific client's numbers, a topic the docs do not cover, and advisory work) |

Every heading has an explicit anchor (`{ #anchor }`), so the existing chunker produces stable section ids like `payment-approval#changed-bank-details`, and the golden set points at those ids.

`tests/test_finance_demo.py` checks, without a database or network, that every golden answer points at a section the chunker really produces, that ids are unique, and that every document is marked synthetic.

## Status

The corpus and golden set are ready. The retrieval and answer evals have **not** been run on it yet, because the loader is still FastAPI-specific (`src/rag/ingest/loader.py` downloads pinned pages from GitHub). The next step is a small local-folder loader, then `make eval-retrieval` against this golden set. Until that run exists, no quality numbers are claimed for this corpus.
