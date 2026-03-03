# Boston Tea Party 2.0 — Source Data

This directory holds the raw and processed documents that power the RAG pipeline: **IRC**, **IRS Publications**, and **U.S. Tax Court opinions**. Each source is versioned and documented here.

## Layout

| Directory      | Contents |
|----------------|----------|
| `irc/`         | Internal Revenue Code (Title 26) — statute. Hierarchical: title → chapter → subchapter → section. |
| `irs_pubs/`    | IRS Publications (e.g. Pub. 17, 501, 526). Tax-year–specific; numbered headings and worked examples. |
| `tax_court/`   | U.S. Tax Court opinions. Narrative/prose; used for BM25 retrieval. |

## Where data comes from

- **IRC**: [Cornell LII — 26 U.S. Code](https://www.law.cornell.edu/uscode/text/26), or official/legal data providers. Prefer a stable, machine-readable source (e.g. XML or structured HTML) for parsing.
- **IRS Publications**: [IRS.gov Forms & Pubs](https://www.irs.gov/forms-pubs) — e.g. [Pub. 17](https://www.irs.gov/pub/irs-pdf/p17.pdf), [Pub. 501](https://www.irs.gov/pub/irs-pdf/p501.pdf), [Pub. 526](https://www.irs.gov/pub/irs-pdf/p526.pdf). PDF or HTML; note tax year (e.g. 2024).
- **Tax Court**: [U.S. Tax Court](https://www.ustaxcourt.gov) — opinions and orders. Use sample opinions for BM25 indexing; capture case name, year, and text.

## Versioning

- **IRC**: Note the source date or U.S. Code edition (e.g. annual supplement). Store as `irc/` with optional subdirs by title/chapter if needed.
- **IRS Pubs**: One folder per tax year, e.g. `irs_pubs/2024/`. Filenames should include publication number and year (e.g. `p17_2024.pdf`).
- **Tax Court**: Store by case name or docket; include year. No formal versioning beyond "as of download date."

## Usage

- **Tree-based retrieval** (PageIndex or custom): consumes `irc/` and `irs_pubs/` after parsing into a hierarchical index.
- **BM25 retrieval**: consumes `tax_court/` (and optionally fallback for IRC/Pubs if needed).
- Do not commit large PDFs or full corpora if they exceed repo size; use `.gitignore` for bulk data and document download/update steps here or in `scripts/`.
