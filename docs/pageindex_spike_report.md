# PageIndex spike — result

**File**: `p501_sample.pdf`  
**doc_id**: `pi-cmma55t2r04700jo9fdj0dzaw`

## Tree shape (first 20 nodes)

-  [0000] p.1 — Dependents, Standard Deduction, and Filing Information
-    [0001] p.1 — What's New
-    [0002] p.2 — Reminders
-    [0003] p.2 — Introduction
-    [0004] p.3 — Who Must File
-    [0005] p.5 — Who Should File
-    [0006] p.5 — Filing Status
-      [0007] p.6 — Marital Status
-      [0008] p.6 — Single
-      [0009] p.6 — Married Filing Jointly
-      [0010] p.7 — Married Filing Separately
-      [0011] p.8 — Head of Household
-      [0012] p.10 — Qualifying Surviving Spouse
-    [0013] p.11 — Dependents
-      [0014] p.11 — Exceptions
-      [0015] p.12 — Qualifying Child
-        [0016] p.13 — Relationship Test
-        [0017] p.13 — Age Test
-        [0018] p.13 — Residency Test
-        [0019] p.15 — Support Test (To Be a Qualifying Child)

## Tax-specific parsing

- PageIndex returns a clean hierarchy (title, node_id, page_index, text). For **IRC/IRS Pubs** we still need to attach **section numbers and publication year** for citations (see `docs/structure_analysis.md`).
- **Recommendation**: Use PageIndex for tree build and LLM-based navigation; add a **tax metadata layer** that maps nodes back to IRC § or IRS Pub section from our parser.
