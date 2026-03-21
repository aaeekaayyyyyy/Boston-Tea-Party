# Boston Tea Party 2.0: Evaluation Plan

**Date:** Week 1, February 27 - March 5, 2026

---

## 1. Objectives

This document defines how we measure whether Boston Tea Party 2.0 works. Four questions:

1. Does the constraint engine produce correct eligibility decisions?
2. Does the system generate faithful, grounded responses or hallucinate?
3. Are citations accurate, verifiable, and properly attributed?
4. Does tree-based retrieval outperform BM25 on structured legal documents?

All metrics are computed end-to-end and per-component to isolate where failures originate.

---

## 2. Tools

| Tool | Purpose | Cost |
| ---- | ------- | ---- |
| **RAGAS** | Faithfulness scoring. Decomposes answers into claims, checks each against context. Uses a separate "evaluator LLM" (DeepSeek V3.2) behind the scenes as the grader. | $0-3 |
| **LettuceDetect** | Hallucination detection. Token-level span detection on ModernBERT (396M params). 79.2% F1 on RAGTruth vs. 63.4% for GPT-4 prompting. | $0 |
| **DeBERTa-MNLI** | Citation verification via NLI. Checks whether cited passages entail generated claims. | $0 |
| **eyecite + regex** | Legal citation format validation and existence checking against our corpus. | $0 |
| **HHEM-2.1-Open** | Lightweight hallucination baseline. Deploy Week 2 before LettuceDetect is integrated. | $0 |

Deferred: **DeepEval** (revisit Week 3 if RAGAS is insufficient for constraint scoring).

Evaluated but not selected: ARES (too much setup), TruLens (fewer metrics), Galileo (commercial), LRAGE and LegalBench-RAG (references only).

**Blocker:** The PageIndex spike confirmed tree nodes don't carry IRC section numbers or IRS Pub section/year metadata yet. Without this, citation existence and tax-year checks can't run. Must be resolved by Week 2.

---

## 3. Metrics

### 3.1 Nine metrics

#### Comparison metrics

Metrics 1-2 are measured on our system and both baselines. Metrics 3-6 on our system and Baseline B only.

| # | Metric | Scale | Tool |
|---|--------|-------|------|
| 1 | **Answer correctness** | 0-100% | Exact match or LLM-scored (see `metric_definitions.md`) |
| 2 | **Constraint accuracy** | Precision, recall, F1 | Diff against expected constraint result |
| 3 | **Faithfulness** | 0-1 | RAGAS |
| 4 | **Hallucination rate** | 0-1 (lower = better) | LettuceDetect |
| 5 | **Citation existence rate** | 0-1 | Corpus lookup + eyecite |
| 6 | **Citation F1** | 0-1 | NLI (DeBERTa-MNLI) |

#### Retrieval metrics (tree vs. BM25 only)

| # | Metric | Scale |
|---|--------|-------|
| 7 | **Precision@k** | 0-1 |
| 8 | **MRR** | 0-1 |

#### User study

| # | Metric | Scale |
|---|--------|-------|
| 9 | **Comprehension gain** | Pre/post score delta |

### 3.2 Two baselines

**Baseline A: zero-shot.** Same model (Qwen), same question, no retrieval, no constraints. Answers: "does RAG + constraints add value at all?" Scored on metrics 1-2 only.

**Baseline B: given the right sources.** Same model, same question, but true source passages pasted into the prompt. Answers: "does our retrieval find the right stuff, or would perfect documents handed to the model work just as well?" Scored on all six comparison metrics.

### 3.3 Success criteria

| Metric | Target |
| ------ | ------ |
| Answer correctness | >= 80% |
| Constraint accuracy (F1) | >= 0.90 |
| Faithfulness | >= 0.85 |
| Hallucination rate | <= 0.10 |
| Citation existence rate | >= 0.90 |
| Tree beats BM25 | Positive delta on Precision@k or MRR for IRC/IRS Pubs |

### 3.4 Error taxonomy

When something goes wrong, it falls into one of these buckets. This is how we organize the Week 4 gap analysis.

| Failure type | Example | Component |
| ------------ | ------- | --------- |
| Retrieval miss | Query about section 21(c) but retriever returns section 24 | RAG pipeline |
| Metadata miss | Right text returned but citation field blank or wrong | PageIndex + metadata layer |
| Generator hallucination | LLM invents a deduction limit not in any source | Planning agent |
| Constraint logic error | Engine says "ineligible" when taxpayer qualifies | Constraint engine |
| Routing error | Tax Court question sent to tree retrieval | Agent routing |
| Citation fabrication | Answer cites "IRC section 999" which doesn't exist | Planning agent |

---

## 4. Verification Layer

Sits between generation and final output. Consumes the generated answer, retrieved chunks, and constraint engine output. Produces faithfulness scores, citation verification results, hallucination flags, and an overall verdict (pass / warn / fail).

Pipeline: claim decomposition, citation extraction and format validation, citation-to-chunk mapping, NLI verification per claim, existence check, tax-year check, LettuceDetect span detection, aggregate metrics. Full operational detail in `metric_definitions.md`.

---

## 5. User Study (Week 5)

5-8 participants. Pre/post comprehension scoring on tax scenarios. Begin recruiting Week 3. Target: classmates, friends, anyone who files taxes.

---

## 6. Dependencies

| Item | Status | Owner | Deadline |
| ---- | ------ | ----- | -------- |
| Retrieval interface contract | **Done** | Ayushman + Anthony | Week 1 |
| PageIndex spike | **Done** | Ayushman | Week 1 |
| Structure analysis | **Done** | Ayushman | Week 1 |
| Benchmark schema alignment | Drafted (`benchmark_schema.md`) | Francesco + Jonathan | End of Week 1 |
| Jonathan's 10-15 scenarios | Pending | Jonathan | End of Week 2 |
| True source passage text | Pending | Jonathan + Ayushman/Francesco | End of Week 2 |
| Tax metadata layer for nodes | **Blocker.** Needed for citation eval. | Ayushman + Francesco | Week 2 |
| User study recruitment | Not started | Francesco | Week 3 |

---

## 7. Timeline

| Week | Deliverable |
| ---- | ----------- |
| **1** | This plan + benchmark schema. Share schema with Jonathan. |
| **2** | Eval harness scaffolded. Both baselines run against initial scenarios. HHEM deployed. |
| **3** | Verification layer v1: NLI citation check, existence check, tax-year check, eyecite, LettuceDetect. First end-to-end eval. |
| **4** | Full eval suite. Tree vs. BM25 comparison. Gap analysis by error taxonomy. |
| **5** | User study. Final results. Confidence intervals (need 80+ test cases). |
| **6** | Results slides: system vs. both baselines, tree vs. BM25, user study. |
