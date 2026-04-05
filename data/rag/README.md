# RAG data (`data/rag`)

## `pageindex_irs_tree.json`

Cached PageIndex tree for IRS Publication PDFs. Shape:

```json
{ "result": [ /* root PageIndex nodes */ ], "doc_id": "pi-..." }
```

**Publication / tax year consistency:** The tree is built from a specific PDF edition. Keep `publication_year` in retrieval `options` (and agent facts) aligned with that PDF’s tax year. When the team standardizes on a new tax year or Pub revision, refresh this file from PageIndex so headings match what users cite.

Refresh from the live API (overwrites this file):

```bash
python scripts/refresh_pageindex_tree.py
```

Requires `PAGEINDEX_API_KEY` in the environment or `.env`. Optional: `PAGEINDEX_IRS_DOC_ID`, or `SUBMIT_PDF=1` to upload `sources/irs_pubs/p501_sample.pdf` when the doc is not ready.

## `tax_court_corpus.jsonl`

One JSON object per line (BM25 document). Fields:

| Field | Required | Description |
|-------|----------|-------------|
| `text` | yes | Retrieval passage (aim for 200–900 tokens; split long opinions into multiple lines with distinct `chunk_id`). |
| `case_name` | yes | Short case title. |
| `year` | recommended | Decision year (int). |
| `docket` | recommended | Docket number string. |
| `chunk_id` | optional | Stable id for verification (e.g. `smith-2019-para-3`). |
| `source_url` | optional | Link to opinion PDF/HTML on ustaxcourt.gov. |

### Chunking policy (keep eval comparable)

- **One line = one BM25 document.** Do not merge unrelated cases on one line.
- **Long opinions:** split into multiple lines with the same `case_name`, `year`, `docket`, and **distinct** `chunk_id` (e.g. `durden-2012-170f8-a`, `durden-2012-170f8-b`). Each chunk’s `text` should be a contiguous excerpt (section/paragraph scope), not random sentences from the whole opinion.
- **Metadata:** every line must carry the same docket/year as the source opinion so verification and golden tests stay stable when you add chunks.
- **Placeholders:** avoid fictional dockets; use real case names and dockets when publishing snippets for production eval.

Example line:

```json
{"text": "The court held that ...", "case_name": "Example v. Commissioner", "year": 2020, "docket": "1234-19", "chunk_id": "ex-2020-1", "source_url": "https://www.ustaxcourt.gov/..."}
```

Append validated lines with:

```bash
python scripts/ingest_tax_court_line.py
```

(Or edit the file directly and keep valid JSON per line.)

## `golden_retrieval.jsonl`

Benchmark queries for `eval/rag_golden_test.py` (hit@3-style). Update when ranking or corpora change.

## Verification checklist (minimum metadata per `source_type`)

| source_type | Required fields |
|-------------|-----------------|
| `irs_pubs` | `publication`, `publication_year`, `heading_trail`, `node_id` (PageIndex) |
| `irc` | `citation`, `section`, `source_url` when available |
| `tax_court` | `case_name`, `publication_year` (opinion year), `docket`, `chunk_id` in `node_id` |

Use `src.rag.locator.retrieval_locator(metadata)` for a single normalized locator string (see `docs/retrieval_interface_spec.md`).
