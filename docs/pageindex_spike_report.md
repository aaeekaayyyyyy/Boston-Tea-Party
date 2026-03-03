# PageIndex spike — setup
- Set `PAGEINDEX_API_KEY` (from https://dash.pageindex.ai/api-keys) to run the live spike.
- PageIndex **accepts PDF only**. No PDF found under `sources/irc/` or `sources/irs_pubs/`.
  - Run `python scripts/download_samples.py` (fix SSL if needed) to fetch an IRS Pub PDF, or place any IRC/IRS Pub PDF there.

## Conclusion (without live run)
- **Tax-specific parsing**: For IRC we need **section/subsection metadata** (e.g. 26 USC § 1(c)) in retrieval results for citations. PageIndex tree nodes use `title`, `node_id`, `page_index`, `text`. We should map node titles or add a post-step to attach IRC/IRS section numbers from our structure analysis.
- **Recommendation**: Use PageIndex for tree generation and navigation; add a thin **tax-specific layer** that (1) parses our source types (IRC vs IRS Pub) and (2) enriches node metadata with section/publication/year for the verification layer.
