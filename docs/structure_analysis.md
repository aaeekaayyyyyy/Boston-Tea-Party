# Document Structure Analysis — RAG Pipeline

**Purpose**: Map heading levels, section numbering, and nesting for IRC and IRS Publications so we can build the tree index and choose/adapt PageIndex. Notes for Tax Court inform BM25 chunking and metadata.

---

## 1. Internal Revenue Code (IRC) — Title 26

**Source**: [Cornell LII — 26 U.S. Code](https://www.law.cornell.edu/uscode/text/26), or official US Code data.

### Hierarchy

| Level | Example | Notes |
|-------|---------|--------|
| Title | 26 (Internal Revenue Code) | Single title for tax. |
| Subtitle | Subtitle A — Income Taxes | Top-level division. |
| Chapter | Chapter 1 — Normal Taxes and Surtaxes | Numbered. |
| Subchapter | Subchapter A — Determination of Tax Liability | Lettered (A, B, …). |
| Part | Part I — Tax Imposed | Roman numerals. |
| Section | § 1 — Tax imposed | **§** + number; primary citation unit. |
| Subsection | (a), (b), (c)… | Lettered parentheses. |
| Paragraph | (1), (2)… | Numbered parentheses. |
| Subparagraph | (A), (B)… | Nested lettering. |

### Section structure (e.g. § 1)

- **Heading**: "26 U.S. Code § 1 - Tax imposed"
- **Subsections**: (a) Married individuals…, (b) Heads of households, (c) Unmarried individuals, (d) Married filing separate, (e) Estates and trusts
- **Content**: Tables (e.g. tax brackets), cross-references to other sections (e.g. section 7703, 6013, 2(a)), definitions
- **Navigation**: prev/next links; in bulk data, parent/sibling section IDs or paths

### Parsing notes

- Sections are the main retrieval unit; subsections (a)(b)(c) are natural children in the tree.
- Preserve **section number** and **subsection** in metadata for citations (e.g. `26 USC § 1(c)`).
- Cross-references (e.g. "section 7703") can be resolved to URLs or section IDs for optional linking.
- Tables (tax brackets, limits) are inline; keep with the subsection that contains them.

### Tree index implications

- **Root**: Title 26 → Subtitle → Chapter → Subchapter → Part → **Section** (leaf or near-leaf for retrieval).
- **Granularity**: Section or subsection level; avoid splitting mid-subsection.
- **Metadata per node**: `title`, `chapter`, `subchapter`, `part`, `section`, `subsection`, `source_url` (if applicable).

---

## 2. IRS Publications (e.g. Pub. 17, 501, 526)

**Source**: [IRS.gov Forms & Pubs](https://www.irs.gov/forms-pubs) — PDF or HTML; tax-year–specific (e.g. 2024).

### Hierarchy

| Level | Example | Notes |
|-------|---------|--------|
| Publication | Pub. 17 — Your Federal Income Tax | Whole document. |
| Chapter | Chapter 1 — Filing Information | Numbered. |
| Major heading | Who Must File | Bold or large font. |
| Numbered heading | 1.1, 1.2… or 1, 2, 3… | Varies by pub. |
| Sub-heading | Worked examples, "Example 1" | Often in boxes or indented. |

### Typical structure

- **Front matter**: Title, tax year, table of contents.
- **Chapters**: High-level topics (filing, income, deductions, etc.).
- **Numbered sections**: Within chapters; some pubs use decimal numbering (1.1, 1.2).
- **Worked examples**: "Example 1", "Example 2" — important for RAG; keep as blocks with labels.
- **Tables and worksheets**: Similar to IRC; keep with the section that references them.

### Parsing notes

- **Tax year**: Must be in metadata (e.g. `publication_year: 2024`) for correctness and verification.
- **Publication number**: e.g. `p17`, `p501`, `p526` — required for citations.
- If PDF: use a PDF-to-structure pipeline (e.g. heading detection, outline) to get hierarchy; PageIndex may consume PDF directly — verify during spike.
- If HTML: map `<h1>`–`<h6>` and class names to the levels above.

### Tree index implications

- **Root**: Publication → Chapter → Section/heading → Example or paragraph.
- **Metadata per node**: `publication`, `publication_year`, `chapter`, `section_or_heading`, `example_id` (if applicable).

---

## 3. U.S. Tax Court Opinions

**Source**: [U.S. Tax Court](https://www.ustaxcourt.gov) — opinions and orders; narrative/prose.

### Structure (narrative)

| Element | Notes |
|--------|--------|
| Case name | e.g. *Smith v. Commissioner* |
| Docket number | Case identifier. |
| Date / year | Decision date. |
| Judge | Author of opinion. |
| Headings | Often "Background", "Discussion", "Conclusion" — not as rigid as IRC. |
| Paragraphs | Long prose; citations to IRC, regs, other cases. |

### Parsing notes for BM25

- **Metadata to extract**: `case_name`, `docket`, `year`, `judge` (optional).
- **Chunking**: Paragraph or multi-paragraph chunks (e.g. 200–500 tokens); avoid splitting mid-sentence.
- **No deep tree**: Use flat or shallow structure; BM25/keyword over paragraph-level chunks.
- Store raw text and metadata so retrieval can return "Case X (Year)" and optional paragraph or page ref.

### BM25 implications

- Index: one document per opinion or per major section; fields: `text`, `case_name`, `year`, `docket`.
- Retrieval returns ranked chunks + `case_name`, `year`, and preferably a snippet or paragraph ID for citation.

---

## 4. Summary for retrieval

| Source | Primary retrieval | Metadata to return |
|--------|-------------------|--------------------|
| IRC | Tree (PageIndex or custom) | `section` (e.g. 26 USC § 1(c)), optional `subsection` |
| IRS Pubs | Tree (PageIndex or custom) | `publication`, `publication_year`, `chapter`, `section_or_heading` |
| Tax Court | BM25 | `case_name`, `year`, `docket`, chunk/snippet ref |

---

*Next: Run PageIndex spike on one IRC section or one IRS Pub to confirm default behavior vs. tax-specific parsing needs.*
