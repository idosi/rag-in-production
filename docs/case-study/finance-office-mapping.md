# Mapping the system onto a small finance office

The scenario: a small bookkeeping firm, about 10 to 20 staff, wants an internal assistant that answers questions from its own policies and procedures. This is a **hypothetical client**, used to design and stress-test the reference implementation. A synthetic corpus and golden set for it are in [examples/finance-office/](../../examples/finance-office/).

For each concern below: what the code does today (with the file), and what would change for a real firm.

## 1. Document sources

| Today | For a finance office |
|---|---|
| `src/rag/ingest/loader.py` downloads 48 pinned FastAPI pages from GitHub, inlines code examples, and caches them on disk | Policies live in Word, PDF and a shared drive or SharePoint. Add loaders that convert them to Markdown with headings preserved, because the chunker splits on headings |
| Every page has a stable id and a deep link per section | Same idea: a document id plus a section anchor, and a link back to the document in the firm's system |
| Re-ingest skips unchanged pages (content hash that includes chunk size, overlap and embedding model) and deletes pages that disappeared upstream | Exactly what a policy library needs: a withdrawn policy must stop being cited. Add the policy's version and effective date to the chunk metadata and show them in the citation |
| Corpus pinned to one docs version | One "published" version of the policy library at a time. Draft policies are not ingested |

The synthetic corpus uses explicit heading anchors (`## Legal hold { #legal-hold }`), so the existing chunker produces section ids like `document-retention#legal-hold` with no code change. `tests/test_finance_demo.py` proves it.

## 2. Confidentiality and where data goes

| Today | For a finance office |
|---|---|
| Embeddings run locally (`fastembed`), so document text is not sent to an embeddings API | Keep it. Only the 5 retrieved sections and the question go to the LLM provider |
| The question text is not logged, only its length (`api.py`, `trace.py`) | Keep it in the operational log. The audit log (section 5) is a separate, access-controlled store |
| Database and API both in Frankfurt | Choose the region by the firm's data-residency rules; check the LLM provider's data-retention terms before go-live |
| Secrets in Secret Manager, database password redacted from logs, TLS required for a remote database (`dburl.py`) | Same |

## 3. Personal data (PII)

Internal policies should contain no client personal data, but in practice examples and templates leak it (a real ID number in a sample form).

- **At ingest:** a redaction pass for ID numbers, bank account numbers and email addresses before chunking, with a report of what was redacted, so a person reviews it. Not built yet.
- **In questions:** staff will type client names and numbers into the question. The policy in the synthetic corpus already says to use client codes (`CL-0142`) instead of names. The system should not store question text outside the audit log.
- **Scope rule:** the assistant answers questions about the firm's rules, not about a specific client's data. The golden set tests this: "What was client CL-0142's revenue last year?" must be refused (`u02`).

## 4. Refusal on unanswerable questions

| Today | For a finance office |
|---|---|
| The system prompt requires one exact refusal sentence when the sources do not answer (`generator.py`, `NOT_FOUND`) | Same mechanism, with the firm's wording and an escalation: "I couldn't find this in the firm's policies. Ask the policy owner: Finance Lead." Each document already names its owner |
| No threshold on similarity score, because an unanswerable question scored higher (0.765) than an answerable one (0.729) | Same reasoning applies |
| "Not found" answers are never cached | Same |
| 6 unanswerable questions in the golden set | The synthetic set has 4, of four kinds: a live tax rate (`u01`, must come from the authority, not from memory), a specific client's numbers (`u02`), a topic the docs do not cover (`u03`), and advisory work (`u04`, "should my client incorporate?") |

The system prompt and refusal sentence are hard-coded for FastAPI today. For a second domain they move into configuration (domain name, refusal sentence, escalation contact), and the evals read the same configuration so the exact-match check still works.

## 5. Citations and audit trail

| Today | For a finance office |
|---|---|
| Every claim cites `[n]`; each source carries a deep link to its section; phantom citations (a number with no source) are detected | Add policy version and effective date to each citation, so a reviewer can tell which rule applied on the day |
| One JSON trace line per question: request id, timings, cost, cache hit, model, status | Add a separate **audit log**: user, time, question, the section ids shown, the answer, and the model. Stored in its own table with restricted access and a retention period. Operational logs stay free of question text |
| | A "this answer was wrong" button that writes to the audit log; flagged answers become new golden-set questions |

## 6. Access control

| Today | For a finance office |
|---|---|
| Shared API keys (`X-API-Key`), rate limit per key | SSO (OIDC) with a real user identity, because the audit log needs a person, not a key |
| Every chunk is visible to every caller | Each document gets an access label (for example `all-staff`, `partners-only`). Retrieval filters **inside the SQL query** (`WHERE access_label = ANY(:user_labels)`) before ranking, never after the model sees the text. A test asserts that a bookkeeper's question never retrieves a partners-only section |
| | The cache key includes the user's access labels, otherwise a partner's cached answer could reach a bookkeeper |

## 7. Retrieval in this domain

Finance documents contain exact identifiers: client codes (`CL-0142`), account numbers (`9999`), amounts and thresholds. On the FastAPI docs, hybrid search (keywords + vectors) did not help, because questions were natural language over prose. On this corpus it may. This is a testable hypothesis, not a claim: the synthetic golden set has `code-name` questions (`f06`, `f13`) for exactly this reason. The plan is to run `vector`, `hybrid`, `rerank` and `hybrid_rerank` on it and keep whichever wins without breaking questions, as in step 2b.

Tables matter too: approval limits and retention periods are tables. The chunker splits a section at blank lines, so a table (no blank lines inside) stays in one chunk unless it is longer than the chunk size. The synthetic documents include tables so the evals exercise this.

## 8. Cost at this scale

At about $0.007 per question on Sonnet, 15 staff asking 10 questions a day is about $1 a day before the cache, roughly $20 to $25 a month. The daily budget (`DAILY_BUDGET_USD`) and the budget alert keep a bug or a leaked key from turning that into a surprise. This is an estimate from the measured per-question cost, not a measured monthly bill.

## 9. What is built vs. what is design

| Item | Status |
|---|---|
| Sources-only answers, citations, exact refusal, phantom-citation check | Built and measured (FastAPI corpus) |
| Local embeddings, no question text in logs, secrets, TLS, redaction of DB password | Built |
| Budget, cache, rate limit, alerts, keyless CD | Built and running in the cloud |
| Synthetic finance corpus (8 documents) and golden set (22 questions) | Built, validated by tests, **not yet evaluated** |
| Local-folder / Word / PDF loader | Design |
| Domain configuration for prompt and refusal | Design |
| Per-document access control, SSO, audit log, PII redaction at ingest | Design |
