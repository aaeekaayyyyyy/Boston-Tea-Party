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

For each citation in the response, check: (1) does the cited source exist in our corpus? (2) is the citation in valid legal format? Uses eyecite for case law format and regex for IRC sections and Treasury Regulations.

Score = citations pointing to real, correctly-formatted sources / total citations.

## Citation F1

We use cited sentences as the evaluation unit (sentence-level approximation of atomic claims).

For each sentence with one or more citations, feed the sentence as hypothesis and the cited passage(s) as premise into DeBERTa-MNLI. Entailment = supported. Neutral or contradiction = unsupported.

**Citation recall** is measured against citation-required sentences: answer sentences containing legal or factual claims depending on source material (thresholds, rates, deadlines, eligibility rules, publication guidance, case holdings, cross-references to other IRC sections). Recall = citation-required sentences with at least one valid supporting citation / total citation-required sentences.

**Citation precision** uses a drop-one necessity test. For each cited sentence, remove one citation at a time and re-run entailment. If entailment still holds, the removed citation was unnecessary. Precision = necessary citations / total citations provided.

**Citation F1** = harmonic mean of precision and recall.

## Precision@k and MRR

Standard IR metrics. Run the same questions through both retrieval paths (tree and BM25). The retrieval interface returns `strategy` per response, so the harness automatically tags which path was used.

Compare tree on IRC/IRS Pubs vs. BM25 on the same docs, and vice versa, to validate the hybrid design.

## Comprehension gain

Pre/post scoring. Participant reads a tax scenario, answers comprehension questions (pre-score), interacts with the system, answers again (post-score). Gain = post minus pre.

---

## Verification layer pipeline (build reference for Week 3)

1. **Claim decomposition:** Break answer into atomic claims (RAGAS evaluator LLM call).
2. **Citation extraction:** Parse inline citations. Validate format with regex + eyecite.
3. **Citation mapping:** Look up each citation in retrieval output using `citation` and `source_type` metadata.
4. **NLI verification:** For each (claim, cited passage) pair, run DeBERTa-MNLI for entailment.
5. **Existence check:** Verify cited sources exist in corpus.
6. **Tax-year check:** For IRS Pub citations, verify `publication_year` matches scenario tax year.
7. **Span detection:** Run LettuceDetect on full (context, answer) pair.
8. **Aggregate:** Compute all six comparison metrics.
