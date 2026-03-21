# Benchmark Schema

Format for the evaluation benchmark scenarios. Jonathan provides the core fields (tax expertise). Francesco augments with eval infrastructure fields afterward.

---

## What Jonathan provides per scenario

```json
{
  "id": "TC-001",
  "question": "A married couple filing jointly in 2025 has AGI of $145,000 and two qualifying children ages 5 and 8. They paid $12,000 in child care expenses. What is their maximum Child and Dependent Care Credit?",
  "answer": "$1,200",
  "required_citations": ["IRC §21(a)", "IRC §21(c)", "IRC §21(a)(2)"],
  "constraint_result": {
    "eligible": true,
    "conditions_met": ["filing_status_valid", "qualifying_dependents", "expenses_incurred"]
  }
}
```

Four required fields:

- **question**: the tax scenario
- **answer**: the correct answer
- **required_citations**: which sources should be cited
- **constraint_result**: what the constraint engine should output

Add whatever else is useful (taxpayer profile, notes, etc.) but those four are what the eval harness needs.

---

## What gets added after

Once scenarios are in, I augment each with fields for the eval harness and baseline comparison:

- **true_source_passages**: actual IRC/IRS Pub text for each required citation, pulled from corpus. Used as context when scoring Baseline B through RAGAS and LettuceDetect.
- **question_type**: calculation, factual lookup, eligibility determination, multi-step reasoning, planning scenario, or adversarial/edge case.
- **source_type**: irc, irs_pubs, or tax_court.
- **difficulty**: easy, medium, hard.
- **component_tested**: which system components the scenario exercises.

---

## Question type targets

| Type                      | Count | Primary component tested       |
| ------------------------- | ----- | ------------------------------ |
| Factual lookup            | ~3-4  | Retrieval                      |
| Calculation               | ~3-4  | Constraint engine + generation |
| Eligibility determination | ~3-4  | Constraint engine              |
| Multi-step reasoning      | ~2-3  | Full pipeline                  |
| Planning scenario         | ~1-2  | Planning agent                 |
| Adversarial / edge case   | ~1-2  | Verification layer             |

Cover all three data sources: IRC (tree), IRS Publications (tree), Tax Court opinions (BM25). Reference sections we know are in the corpus (e.g. Pub. 501 headings from the PageIndex spike).

---

## Expansion plan

10-15 expert-authored scenarios in Weeks 1-2 are the seed set. Expand to 80-100+ by Week 4 by generating perturbations: vary AGI, filing status, number of dependents, and tax year on each seed scenario. Gets us enough test cases for meaningful confidence intervals without requiring 100 hand-written scenarios.

---

## Scoring

~60% binary: factual lookups, eligibility yes/no, calculations with single correct answers.

~40% rubric-based partial credit for multi-step and planning scenarios:

| Score | Label     | Criteria                                                 |
| ----- | --------- | -------------------------------------------------------- |
| 2     | Correct   | Right answer with valid citations                        |
| 1     | Partial   | Correct direction but missing citations or minor errors  |
| 0     | Incorrect | Wrong answer, fabricated citations, or wrong legal basis |

For LLM-scored rubric items: use named categories ("Correct / Partial / Incorrect") rather than numeric scales.
