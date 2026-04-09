"""
Rule-aligned advisory layer: taxpayer position, IRS forms/schedules, and smart follow-ups.
Grounded in SimpleConstraintEngine outcomes + optional facts (mirrors src/rules themes).
Not legal advice—educational pointers to official IRS forms and publications.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .intake import has_any_charitable_contribution


def _federal_residency(facts: Dict[str, Any]) -> Optional[str]:
    v = facts.get("federal_tax_residency")
    if isinstance(v, str) and v.strip():
        return v.strip().lower().replace(" ", "_")
    return None


def _likely_form_8843_scenario(facts: Dict[str, Any]) -> bool:
    """
    Educational heuristic: many nonresident students / exempt individuals file Form 8843 even with no income.
    See IRS Form 8843 instructions—not legal advice.
    """
    res = _federal_residency(facts)
    stu = _tri(facts, "is_student_in_us")
    visa = _tri(facts, "us_student_visa_f1_j1_m")
    if res == "nonresident_alien":
        if visa is True:
            return True
        if stu is True:
            return True
    if res == "unsure" and (stu is True or visa is True):
        return True
    return False


def _tri(facts: Dict[str, Any], key: str) -> Optional[bool]:
    v = facts.get(key)
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return None


def _float_or_none(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_taxpayer_position(
    facts: Dict[str, Any],
    constraint_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Human-readable position given known facts and engine valid_paths.
    """
    ms = facts.get("marital_status_on_1231")
    joint = facts.get("spouse_willing_to_file_jointly")
    lived = facts.get("lived_with_spouse_last_6_months")
    valid_paths = list(constraint_result.get("valid_paths") or [])
    unresolved = constraint_result.get("unresolved_constraints") or []
    res = _federal_residency(facts)
    stu = _tri(facts, "is_student_in_us")
    visa = _tri(facts, "us_student_visa_f1_j1_m")
    below_thr = _tri(facts, "income_below_us_filing_threshold")
    state_live = (facts.get("primary_state_of_residence") or "").strip()

    headline = "Position not yet determined"
    detail_parts: List[str] = []
    confidence = "low"
    intl_student_headline = False

    # --- Residency / student path (overrides generic "single filer" framing when relevant) ---
    if stu is True or visa is True:
        if res in (None, "unsure"):
            headline = "**Residency for tax purposes** needs to be determined (student context)"
            intl_student_headline = True
            detail_parts.append(
                "U.S. **federal tax residency** (resident vs. **nonresident alien**) is separate from immigration status. "
                "Students in the U.S. often use **IRS Pub. 519** and the **substantial presence test** (with **exempt-days** rules for many F/J/M students) to decide how to file."
            )
            if state_live:
                detail_parts.append(
                    f"You indicated living mostly in **{state_live}**; **state** tax residency and filing can differ from **federal** rules—confirm separately."
                )
            confidence = "low"
        elif res == "nonresident_alien":
            headline = "Likely **nonresident alien** posture—domestic **Single** filing rules may not apply"
            intl_student_headline = True
            detail_parts.append(
                "If you are a **nonresident alien** for U.S. tax, **Form 1040** filing-status boxes for U.S. residents may **not** describe your return. "
                "Many students on **F-1/J-1/M-1**-type statuses must file **Form 8843** (Statement for Exempt Individuals…) when required, **even with no income**—follow the form instructions for your year."
            )
            if below_thr is True:
                detail_parts.append(
                    "With **no income** (or under the filing threshold), you may still have an **information filing** like **Form 8843**; do **not** assume “no 1040” means “nothing to file.”"
                )
            elif below_thr is False:
                detail_parts.append(
                    "If you have **U.S.-source income**, you may need a **1040-NR** (or other nonresident forms) per Pub. **519**—not a standard resident **1040** in many cases."
                )
            detail_parts.append(
                "**Pub. 519** (U.S. Tax Guide for Aliens) is the primary IRS overview; verify every year’s thresholds and exceptions."
            )
            confidence = "medium" if visa is True or stu is True else "low"
        elif res in {"us_citizen_or_national", "us_resident_alien"}:
            detail_parts.append(
                "As a **U.S. citizen or resident alien** for tax, you generally follow the same **Form 1040** / Pub. **501** filing-status rules as other domestic filers (student status alone does not change that)."
            )
            if state_live:
                detail_parts.append(
                    f"State of residence **{state_live}** may have its own return rules (e.g. residency for state tax)."
                )
            confidence = "medium"

    if ms is None:
        headline = "Awaiting marital status (Dec. 31)"
        detail_parts.append(
            "Filing status is chosen on **Form 1040** and depends on whether you were married, "
            "unmarried, or a surviving spouse on the last day of the tax year (see IRS Pub. **501**)."
        )
        confidence = "low"
    elif ms == "married":
        if joint is True:
            headline = "Likely posture: **Married filing jointly**"
            detail_parts.append(
                "You indicated you plan to file jointly. One **Form 1040** typically covers both spouses; "
                "both must sign if filing on paper. Income and deductions are combined per instructions."
            )
            confidence = "medium" if not unresolved else "low"
        elif joint is False:
            if lived is False and "head_of_household" in valid_paths:
                headline = "Open paths: **Married filing separately** and possible **Head of household**"
                detail_parts.append(
                    "You may file **Married filing separately** on your own **Form 1040**. "
                    "If you meet **considered unmarried** rules and HoH tests (qualifying person, pay > half "
                    "cost of keeping up home), **Head of household** may yield a better outcome—verify in Pub. **501**."
                )
                confidence = "medium"
            else:
                headline = "Likely posture: **Married filing separately** (joint not elected)"
                detail_parts.append(
                    "Without a joint election, each spouse generally files a separate **Form 1040** as **MFS**. "
                    "Several credits and deductions are limited on MFS returns; compare to MFJ if still possible."
                )
                confidence = "medium" if lived is not None else "low"
        else:
            headline = "Married—**joint vs. separate** still open"
            detail_parts.append(
                "Whether you file one joint return or two separate returns changes brackets, standard deduction, "
                "and eligibility for certain credits. Answer the joint-filing question to narrow the path."
            )
            confidence = "low"
    elif ms in {"single", "divorced", "legally_separated", "widowed"}:
        if intl_student_headline:
            detail_parts.append(
                "You are **unmarried** for Dec. 31. If you are **nonresident** or still determining residency, "
                "prioritize **Pub. 519**, **Form 8843**, and **1040-NR** (if income)—not the usual resident **Single** **1040** narrative alone."
            )
        else:
            headline = "Primary open path: **Single** (verify HoH / QSS if applicable)"
            detail_parts.append(
                "For an unmarried taxpayer, **Single** is the usual filing status on **Form 1040** unless you qualify for "
                "**Head of household** (qualifying person + cost-of-home tests) or **Qualifying surviving spouse** "
                "(see Pub. **501**)."
            )
            confidence = "medium"

    path_expl = []
    for p in valid_paths:
        path_expl.append(
            {
                "path_id": p,
                "label": p.replace("_", " ").title(),
                "note": _path_note(p),
            }
        )

    return {
        "headline": headline,
        "detail": "\n\n".join(detail_parts),
        "valid_paths": valid_paths,
        "path_explanations": path_expl,
        "confidence": confidence,
        "rules_index_note": "Full rule dependency order is documented in src/rules/index.yaml (filing status → income → deductions → credits → payments → documentation).",
    }


def _path_note(path_id: str) -> str:
    return {
        "single": "Form 1040 filing status box: Single.",
        "married_filing_jointly": "One return; combined income and deductions.",
        "married_filing_separately": "Separate returns; watch credit/deduction limits.",
        "head_of_household": "Often higher standard deduction than Single; strict eligibility tests.",
    }.get(path_id, "See IRS Pub. 501.")


def recommend_forms_and_schedules(
    facts: Dict[str, Any],
    constraint_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Ordered list of forms with when they apply and how to approach them (high level).
    """
    valid_paths = set(constraint_result.get("valid_paths") or [])
    active_rules = set(constraint_result.get("active_rules") or [])
    ty = facts.get("tax_year") or "the year"

    item_total = _float_or_none(facts.get("itemized_deductions_total"))
    item_exceeds = _tri(facts, "itemized_deductions_exceed_standard")
    has_charity = has_any_charitable_contribution(facts)
    noncash = _float_or_none(facts.get("charitable_noncash_contributions")) or 0
    cash = _float_or_none(facts.get("charitable_cash_contributions")) or 0

    w2 = _tri(facts, "has_w2_income")
    se = _tri(facts, "has_self_employment_income")
    interest_div = _tri(facts, "has_interest_or_dividend_income")
    cap_gains = _tri(facts, "has_capital_asset_sales")
    dep_u17 = _tri(facts, "has_qualifying_children_under_17")
    age65 = _tri(facts, "taxpayer_age_65_or_older")
    blind = _tri(facts, "taxpayer_blind")
    salt = _tri(facts, "paid_state_local_taxes")
    medical = _tri(facts, "had_significant_medical_expenses")

    forms: List[Dict[str, Any]] = []
    res_tax = _federal_residency(facts)
    below_thr = _tri(facts, "income_below_us_filing_threshold")
    nra = res_tax == "nonresident_alien"
    stu = _tri(facts, "is_student_in_us")
    visa = _tri(facts, "us_student_visa_f1_j1_m")

    def add(form: str, title: str, when: str, steps: List[str], link: str) -> None:
        forms.append(
            {
                "form": form,
                "title": title,
                "when_applies": when,
                "how_to_fill": steps,
                "irs": link,
            }
        )

    if _likely_form_8843_scenario(facts):
        add(
            "8843",
            "Statement for Exempt Individuals and Individuals With a Medical Condition",
            "Many **nonresident** students and exchange visitors in **exempt-individual** years must file **Form 8843** when required by the instructions—**even with no income**.",
            [
                "Read the form instructions for your tax year; complete **identifying information** and the **student/trainee** section that applies.",
                "File **by the due date** in the instructions (mailing address is in the instructions; if you also file **1040-NR**, follow attachment rules there).",
                "Keep a copy; this form supports **substantial presence** / exempt-individual compliance—it is **not** a substitute for **1040-NR** if you had taxable U.S.-source income.",
            ],
            "https://www.irs.gov/forms-pubs/about-form-8843",
        )

    if nra and below_thr is False:
        add(
            "1040-NR",
            "U.S. Nonresident Alien Income Tax Return",
            f"Nonresident aliens with **U.S.-source income** that meets filing thresholds for {ty} typically use this form (not Form 1040).",
            [
                "Use **Pub. 519** to confirm you are **nonresident** and which income is effectively connected or fixed/periodic.",
                "Follow the 1040-NR instructions for exemptions, treaties, and state interactions.",
            ],
            "https://www.irs.gov/forms-pubs/about-form-1040-nr",
        )

    if nra or res_tax == "unsure" or visa is True or (stu is True and res_tax in (None, "unsure")):
        add(
            "Pub. 519",
            "U.S. Tax Guide for Aliens",
            "Explains **resident vs. nonresident** determination, **exempt individuals**, income sourcing, and which forms to file.",
            [
                "Work through **resident vs nonresident** rules before assuming **Form 1040** or **standard deduction** rules apply.",
                "Students: pay attention to **exempt days** under the **substantial presence test** and any **Form 8843** filing requirement.",
            ],
            "https://www.irs.gov/publications/p519",
        )

    when_1040 = (
        f"**U.S. citizens and resident aliens** use Form 1040 for {ty}. **Nonresidents** generally use **1040-NR** and/or **8843**, not this form, unless a special election applies (Pub. 519)."
        if nra
        else f"Almost all **U.S. citizen and resident** individual filers for {ty}."
    )
    steps_1040 = [
        "Enter name, **SSN or ITIN**, address, and **filing status** (Pub. 501 for residents).",
        "Wage earners: **Form W-2**; self-employed: **Schedule C**; follow attached schedules as needed.",
        "Sign and date (both spouses if MFJ); e-file when possible.",
    ]
    if nra:
        steps_1040.insert(
            0,
            "If you are **nonresident**, you usually **do not** use Form 1040—use **1040-NR** and/or **8843** per Pub. 519 instead.",
        )
    add(
        "1040",
        "U.S. Individual Income Tax Return",
        when_1040,
        steps_1040,
        "https://www.irs.gov/forms-pubs/about-form-1040",
    )

    likely_itemize = (
        item_exceeds is True
        or (item_total is not None and item_total > 0 and item_exceeds is not False)
    )
    if likely_itemize or (has_charity and item_total is not None and item_total > 0):
        add(
            "Schedule A (Form 1040)",
            "Itemized Deductions",
            "You indicated itemized deductions or provided an itemized total to compare to the standard deduction.",
            [
                "Complete only if **total itemized deductions exceed your standard deduction** for your filing status.",
                "Charitable gifts: cash vs. noncash; over **$250** generally needs written acknowledgment per instructions.",
                "Mortgage interest on **Form 1098**, state/local taxes (SALT limits apply), medical over AGI threshold, etc.",
            ],
            "https://www.irs.gov/forms-pubs/about-schedule-a-form-1040",
        )
    elif has_charity and item_total is None:
        add(
            "Schedule A (Form 1040)",
            "Itemized Deductions",
            "You have charitable contributions—itemizing may be worthwhile if total Schedule A items exceed the standard deduction.",
            [
                "Total **all** Schedule A categories; compare to the **standard deduction** for your filing status (Pub. 501 tables).",
                "If you do **not** itemize, charitable contributions are generally **not** deducted on Schedule A (exceptions rare for individuals).",
            ],
            "https://www.irs.gov/forms-pubs/about-schedule-a-form-1040",
        )

    if noncash > 500 or (has_charity and noncash > 0):
        add(
            "8283",
            "Noncash Charitable Contributions",
            "Generally when claiming **noncash** charitable contributions over **$500** (see form instructions).",
            [
                "Sections A/B depend on type and value of property; appraisals may be required for higher values.",
                "Attach to return when required; keep contemporaneous records.",
            ],
            "https://www.irs.gov/forms-pubs/about-form-8283",
        )

    if w2 is True:
        add(
            "W-2",
            "Wage and Tax Statement",
            "You indicated **W-2 wages**; employers provide Form W-2.",
            [
                "Verify Box 1 wages, federal withholding; import or enter each W-2 in software.",
                "Multiple jobs: combine all W-2s; follow 1040 instructions for total wages.",
            ],
            "https://www.irs.gov/forms-pubs/about-form-w-2",
        )

    if se is True:
        add(
            "Schedule C (Form 1040)",
            "Profit or Loss From Business",
            "Self-employment or sole proprietor business income.",
            [
                "Report gross receipts and ordinary/necessary business expenses per instructions.",
                "May need **Form 1099-NEC/1099-K** to reconcile income.",
            ],
            "https://www.irs.gov/forms-pubs/about-schedule-c-form-1040",
        )
        add(
            "Schedule SE (Form 1040)",
            "Self-Employment Tax",
            "Net self-employment income generally over **$400** triggers SE tax calculation.",
            [
                "Schedule SE works with Schedule C; result flows to Schedule 2 / 1040.",
            ],
            "https://www.irs.gov/forms-pubs/about-schedule-se-form-1040",
        )

    if interest_div is True:
        add(
            "Schedule B (Form 1040)",
            "Interest and Ordinary Dividends",
            "Typically when interest/dividends exceed reporting thresholds in instructions.",
            [
                "List payers from **1099-INT** / **1099-DIV**; answer foreign-account questions if applicable.",
            ],
            "https://www.irs.gov/forms-pubs/about-schedule-b-form-1040",
        )

    if cap_gains is True:
        add(
            "Schedule D / Form 8949",
            "Capital Gains and Losses",
            "Sales of stocks, crypto, funds, or other capital assets.",
            [
                "Use **1099-B** proceeds; match lots on **Form 8949** and roll totals to Schedule D.",
                "Holding period determines short- vs. long-term rates on instructions.",
            ],
            "https://www.irs.gov/forms-pubs/about-schedule-d-form-1040",
        )

    if dep_u17 is True:
        add(
            "Schedule 8812 (Form 1040)",
            "Credits for Qualifying Children and Other Dependents",
            "Qualifying children may support **Child Tax Credit** / other credits per rules.",
            [
                "Verify child meets age, relationship, residency, and support tests (Pub. 972 / instructions).",
            ],
            "https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040",
        )

    if age65 is True or blind is True:
        forms.insert(
            1,
            {
                "form": "1040 / Pub. 501",
                "title": "Standard deduction (age 65+ or blind)",
                "when_applies": "Taxpayers 65 or older and/or blind may use a **higher standard deduction** (see Pub. 501 tables).",
                "how_to_fill": [
                    "Check the age/blindness boxes on **Form 1040** per instructions.",
                    "Use the standard deduction table that matches your filing status and tax year.",
                ],
                "irs": "https://www.irs.gov/publications/p501",
            },
        )

    if salt is True and not likely_itemize:
        add(
            "Schedule A note",
            "State and local taxes",
            "SALT deduction is only if you **itemize**; subject to annual limits.",
            [
                "If you take the **standard deduction**, SALT is not separately deducted on Schedule A.",
            ],
            "https://www.irs.gov/taxtopics/tc503",
        )

    if medical is True and not likely_itemize:
        add(
            "Schedule A note",
            "Medical expenses",
            "Medical expenses are itemized; must exceed **AGI percentage** threshold in instructions.",
            [],
            "https://www.irs.gov/taxtopics/tc502",
        )

    add(
        "Pub. 501",
        "Dependents, Standard Deduction, and Filing Information",
        "Supports filing status and dependency rules used by this engine.",
        [
            "Walk through filing status decision tree before finalizing **Form 1040** box.",
        ],
        "https://www.irs.gov/publications/p501",
    )

    if "deduction_documents" in active_rules and has_charity:
        add(
            "Pub. 526",
            "Charitable Contributions",
            "Substantiation and limits for charitable deductions.",
            [
                "Cash vs. property; **$250+** acknowledgment rules; vehicle and inventory special rules.",
            ],
            "https://www.irs.gov/publications/p526",
        )

    return forms


def advisory_followup_questions(
    facts: Dict[str, Any],
    constraint_result: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Smart suggested questions not already asked by the constraint engine (for richer reports).
    """
    suggestions: List[Dict[str, str]] = []
    known_fields = {u.get("field") for u in (constraint_result.get("unresolved_constraints") or [])}

    def suggest(field: str, question: str, why: str) -> None:
        if field in known_fields:
            return
        if facts.get(field) is not None:
            return
        suggestions.append({"field": field, "question": question, "why_matters": why})

    suggest(
        "federal_tax_residency",
        "For **federal income tax**, are you a **U.S. citizen or resident alien**, or a **nonresident alien** (or **unsure**)?",
        "Residency determines **1040 vs 1040-NR**, **standard deduction** eligibility, and whether **Form 8843** applies—see **Pub. 519**.",
    )
    suggest(
        "primary_state_of_residence",
        "Which **U.S. state** did you live in **most of the year** (e.g. **MA**)?",
        "State filing and residency rules are separate from federal; useful context for students.",
    )
    suggest(
        "is_student_in_us",
        "Were you a **student** in the **United States** for any part of the year?",
        "Students on **F-1/J-1/M-1**-type visas often have **Form 8843** and **exempt-day** rules under the substantial presence test.",
    )
    if facts.get("is_student_in_us") is True:
        suggest(
            "us_student_visa_f1_j1_m",
            "Were you in the U.S. chiefly under an **F-1, J-1, M-1**, or similar **student/exchange** status?",
            "Common trigger for **Form 8843** and **nonresident** vs **resident** analysis in **Pub. 519**.",
        )
    suggest(
        "income_below_us_filing_threshold",
        "Did you have **no income**, or income **below the IRS filing threshold** (so no **1040** is required)?",
        "Even with **no 1040**, you may still need **Form 8843** or other **information returns** if you are a **nonresident student**.",
    )
    suggest(
        "has_w2_income",
        "Did you receive **W-2 wages** from an employer this year?",
        "Determines whether to expect **Form W-2** and wage lines on **1040**; distinguishes from self-employment.",
    )
    suggest(
        "has_self_employment_income",
        "Did you have **self-employment** or gig income (net over ~$400)?",
        "Triggers **Schedule C** and often **Schedule SE** per IRS rules.",
    )
    suggest(
        "has_interest_or_dividend_income",
        "Did you have **interest or dividends** (bank/brokerage 1099s)?",
        "May require **Schedule B** above threshold; ties to rules in income/interest_dividend YAML themes.",
    )
    suggest(
        "has_capital_asset_sales",
        "Did you **sell stocks, funds, crypto, or other property** held for investment?",
        "May require **8949 / Schedule D** and matching broker **1099-B**.",
    )
    suggest(
        "has_qualifying_children_under_17",
        "Do you have **children or dependents under 17** who may qualify for the Child Tax Credit?",
        "Feeds credit rules (see taxes_and_credits/child_tax_credit.yaml) and **Schedule 8812**.",
    )
    suggest(
        "taxpayer_age_65_or_older",
        "Were you **age 65 or older** at end of the tax year?",
        "Affects **standard deduction** amount (Pub. 501 tables) and 1040 checkboxes.",
    )
    suggest(
        "taxpayer_blind",
        "Are you **legally blind** as defined by the IRS?",
        "Additional standard deduction if applicable.",
    )
    suggest(
        "paid_state_local_taxes",
        "Did you pay **state/local income or property taxes** you might deduct?",
        "Relevant if **itemizing** (SALT cap); see deductions/salt.yaml theme.",
    )
    suggest(
        "had_significant_medical_expenses",
        "Did you have **large unreimbursed medical expenses**?",
        "Itemized medical deduction only if above AGI floor—see medical_expenses rules.",
    )
    suggest(
        "itemized_deductions_exceed_standard",
        "Do you already know whether **itemized deductions exceed the standard deduction** for your status?",
        "Locks whether **Schedule A** is the main deduction path vs. standard deduction.",
    )

    return suggestions[:16]


def merge_advisory_into_report(
    base_report: Dict[str, Any],
    facts: Dict[str, Any],
    constraint_result: Dict[str, Any],
) -> Dict[str, Any]:
    pos = compute_taxpayer_position(facts, constraint_result)
    forms = recommend_forms_and_schedules(facts, constraint_result)
    extra_q = advisory_followup_questions(facts, constraint_result)

    base_report["taxpayer_position"] = pos
    base_report["forms_and_schedules"] = forms
    base_report["advisory_followups"] = extra_q

    # Enrich narrative sections with position + forms summary (short)
    if base_report.get("how_to_file") and pos.get("detail"):
        base_report["how_to_file"] = (
            f"{pos['headline']}\n\n{pos['detail']}\n\n---\n\n" + base_report["how_to_file"]
        )

    form_summary_lines = [f"• **{f['form']}** — {f['title']}: {f['when_applies']}" for f in forms[:8]]
    if form_summary_lines and base_report.get("deductions"):
        base_report["deductions"] += "\n\n**Forms to review (based on your answers):**\n" + "\n".join(
            form_summary_lines
        )

    if extra_q and base_report.get("final_report"):
        q_lines = "\n".join(f"• {x['question']}" for x in extra_q[:5])
        base_report["final_report"] += (
            f"\n\n**Suggested next questions** (sharpen your return):\n{q_lines}"
        )

    base_report["followups_suggested"] = list(
        dict.fromkeys(
            (base_report.get("followups_suggested") or [])
            + [x["question"] for x in extra_q[:5]]
        )
    )

    return base_report


def enrich_partial_narrative(
    narrative: Dict[str, Any],
    facts: Dict[str, Any],
    constraint_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Add position, forms, and advisory questions when the planner is still asking follow-ups."""
    narrative["taxpayer_position"] = compute_taxpayer_position(facts, constraint_result)
    narrative["forms_and_schedules"] = recommend_forms_and_schedules(facts, constraint_result)
    narrative["advisory_followups"] = advisory_followup_questions(facts, constraint_result)
    return narrative
