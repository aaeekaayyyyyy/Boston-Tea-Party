# Metric Definitions

Implementation reference for the eval harness. This is how each metric actually works in code.

---

## Answer correctness

For numeric answers: exact match against the true answer.

For text answers: the evaluator LLM gets the true answer and the system's response. Prompt: "Does the response contain the same core factual conclusion as the true answer? Yes or no."

Example: true answer is "$1,200."
- "The maximum credit is $1,200 based on the $6,000 expense cap at 20%" = **correct.**
- "The credit would be approximately $2,400 based on the full $12,000 in expenses" = **incorrect** (wrong cap).
- "The credit is $1,200 but only if they file separately" = **incorrect** (right number, wrong condition).

## Constraint accuracy

Each scenario includes an expected constraint result: `"eligible": true/false` plus `conditions_met`. The constraint engine outputs the same structure. Diff directly. For the vanilla LLM, extract the eligibility claim from free text and compare against the same ground truth.

Report precision, recall, and F1 across all scenarios.

## Faithfulness (RAGAS)

RAGAS decomposes the answer into atomic claims (one evaluator LLM call), then verifies each claim against the provided context (second call). Score = supported claims / total claims.

For our system, context = whatever the retrieval layer returned. For Baseline B, context = true source passages from the benchmark.

Target: >= 0.85.

## Hallucination rate (LettuceDetect)

Span detection on each (context, response) pair. Reports token-level and sentence-level rates. Target: <= 0.10 sentence-level.

Key risk in our domain: fabricated IRC section numbers, wrong tax rates/thresholds, incorrect filing deadlines, misattributed court holdings, outdated provisions. These are semantically indistinguishable from correct answers, which is why we use token-level detection rather than embedding-based methods.

## Citation existence rate

Current harness implementation is benchmark-relative, not corpus-global.

For each required benchmark citation, check whether the response includes that citation string after light normalization (case folding, `section-sign` / `section` normalization, `IRC` / `26 USC` normalization, `IRS Pub.` / `IRS Publication` normalization).

This remains strict about section targets. Example: `IRS Pub. 501` does **not** satisfy `IRS Pub. 501, Filing Status - Head of Household`.

Score = matched required citations / total required citations.

## Citation F1

We use block-scoped practical support coverage rather than exact sentence-local inline citation matching.

The answer is split into local support blocks. A citation-bearing lead sentence can support nearby claim sentences in the same block, including numbered list items. Citation-only lines can also attach to the nearest adjacent substantive block.

For each citation-required claim sentence with an active mapped citation:
- first run a deterministic numeric-support heuristic for simple threshold/rate claims (`not over`, `under age`, `at least X%`, `more than half`, simple dollar thresholds)
- if that heuristic cannot prove support, fall back to DeBERTa-MNLI on the cleaned claim sentence against the cited passage

Entailment or heuristic support = supported. Neutral or contradiction = unsupported.

**Citation recall** is measured against citation-required sentences: answer sentences containing legal or factual claims depending on source material (thresholds, rates, deadlines, eligibility rules, publication guidance, case holdings, cross-references to other IRC sections). Recall = citation-required sentences with at least one valid supporting citation / total citation-required sentences.

**Citation precision** is measured on explicit citation uses only. A citation counts as necessary if it supports at least one claim sentence in the local block it governs. Precision = necessary citations / total explicit citations provided.

**Citation F1** = harmonic mean of precision and recall.

## Precision@k and MRR

Standard IR metrics. Run the same questions through both retrieval paths (tree and BM25). The retrieval interface returns `strategy` per response, so the harness automatically tags which path was used.

Compare tree on IRC/IRS Pubs vs. BM25 on the same docs, and vice versa, to validate the hybrid design.

## Comprehension gain

Pre/post scoring. Participant reads a tax scenario, answers comprehension questions (pre-score), interacts with the system, answers again (post-score). Gain = post minus pre.

---

## Verification layer pipeline (build reference for Week 3)

1. **Claim decomposition:** Break answer into atomic claims (RAGAS evaluator LLM call).
2. **Citation extraction:** Match benchmark-required citations in the rendered answer using light normalization.
3. **Citation mapping:** Map matched citations to the benchmark's `true_source_passages`.
4. **Support verification:** For each (claim, cited passage) pair, run the numeric-support heuristic first for simple threshold/rate claims, then fall back to DeBERTa-MNLI.
5. **Existence check:** Score whether the required benchmark citation target appears in the answer.
6. **Tax-year check:** For IRS Pub citations, verify `publication_year` matches scenario tax year.
7. **Span detection:** Run LettuceDetect on full (context, answer) pair.
8. **Aggregate:** Compute all six comparison metrics.
