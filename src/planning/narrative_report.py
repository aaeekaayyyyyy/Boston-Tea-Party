"""
Three-part taxpayer-facing narrative from facts + constraint outcome + retrieval.
Keeps demos readable: short sections, citations as labels—not full RAG dumps.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .tax_advisory import enrich_partial_narrative, merge_advisory_into_report


_DOC_REQ_LABELS: Dict[str, str] = {
    "charitable_acknowledgments": "written acknowledgments for charitable gifts",
    "Schedule_A": "Schedule A (itemized deductions)",
    "medical_records": "medical expense records",
    "1098": "Form 1098 (mortgage interest)",
    "SALT_receipts": "state and local tax records",
}


def _format_doc_requirements(reqs: List[str]) -> str:
    return ", ".join(_DOC_REQ_LABELS.get(r, r.replace("_", " ")) for r in reqs)


def _citation_line(meta: Dict[str, Any]) -> str:
    st = meta.get("source_type") or ""
    cite = meta.get("citation") or ""
    if st == "irc" and meta.get("source_url"):
        return f"{cite}"
    return cite or st or "Source"


def _top_citations_per_call(retrieval_results: List[Dict[str, Any]], max_calls: int = 8) -> List[str]:
    out: List[str] = []
    for res in retrieval_results[:max_calls]:
        chunks = res.get("chunks") or []
        if not chunks:
            if res.get("retrieval_empty"):
                out.append("(No passage returned for this query.)")
            continue
        m = (chunks[0].get("metadata") or {}) if chunks else {}
        out.append(_citation_line(m))
    return out


def _compact_retrieval_results(
    retrieval_results: List[Dict[str, Any]],
    *,
    max_chunks_per_call: int = 1,
    max_chars: int = 420,
) -> List[Dict[str, Any]]:
    """Shallow copy with truncated chunks for UI cards."""
    compact: List[Dict[str, Any]] = []
    for res in retrieval_results:
        r = dict(res)
        chunks = []
        for ch in (res.get("chunks") or [])[:max_chunks_per_call]:
            c = dict(ch)
            t = c.get("text") or ""
            if len(t) > max_chars:
                c["text"] = t[:max_chars].rstrip() + "…"
            chunks.append(c)
        r["chunks"] = chunks
        compact.append(r)
    return compact


def build_narrative_report(
    facts: Dict[str, Any],
    constraint_result: Dict[str, Any],
    retrieval_calls: List[Dict[str, Any]],
    retrieval_results: List[Dict[str, Any]],
    *,
    use_llm: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Returns:
      how_to_file, deductions, final_report (each plain text),
      source_citations (short list),
      followups_suggested (hints for the UI when still partial context).
    """
    ty = facts.get("tax_year")
    year_bit = f" For tax year {ty}." if ty else ""

    valid_paths = list(constraint_result.get("valid_paths") or [])
    active_rules = list(constraint_result.get("active_rules") or [])
    doc_req = list(constraint_result.get("documentation_requirements") or [])
    ms = facts.get("marital_status_on_1231")
    joint = facts.get("spouse_willing_to_file_jointly")
    lived = facts.get("lived_with_spouse_last_6_months")
    item_total = facts.get("itemized_deductions_total")
    charity_doc = facts.get("charitable_contributions_documented")
    cash = facts.get("charitable_cash_contributions") or 0
    noncash = facts.get("charitable_noncash_contributions") or 0
    has_charity = (cash or 0) > 0 or (noncash or 0) > 0

    residency = facts.get("federal_tax_residency")
    if isinstance(residency, str):
        residency = residency.strip().lower().replace(" ", "_")
    stu_in_us = facts.get("is_student_in_us")
    visa_stu = facts.get("us_student_visa_f1_j1_m")
    state_live = (facts.get("primary_state_of_residence") or "").strip()
    below_thr = facts.get("income_below_us_filing_threshold")

    # --- How to file ---
    filing_parts: List[str] = []

    if state_live:
        filing_parts.append(
            f"You indicated **{state_live}** as the state where you lived most of the year. "
            "**State** income-tax residency and filing (for example, in **Massachusetts**) are **separate** from **federal** rules—check the state DOR if applicable."
        )

    if stu_in_us is True or visa_stu is True:
        if residency == "nonresident_alien":
            filing_parts.append(
                "You indicated **nonresident alien** status for **federal** tax with a **student or F/J/M-type** situation. "
                "In that posture, **Form 8843** is often required **even when you have no income** (see the form’s instructions for your year). "
                "A **Form 1040** “Single” narrative for **residents** may **not** apply; **Pub. 519** and **1040-NR** (if you had U.S.-source income) are the usual references."
            )
            if below_thr is True:
                filing_parts.append(
                    "**No Form 1040** does **not** always mean **nothing to file**—confirm whether **8843** (or other information returns) is still due."
                )
        elif residency in {None, "", "unsure"}:
            filing_parts.append(
                "You indicated a **U.S. student or exchange-visitor** profile but **federal tax residency** is **not** pinned down yet. "
                "Before treating yourself like a typical **domestic Single** filer, work through **IRS Pub. 519** (resident vs. **nonresident**, substantial presence, **exempt days**, and **Form 8843**)."
            )
        elif residency in {"us_citizen_or_national", "us_resident_alien"}:
            filing_parts.append(
                "As a **U.S. citizen or resident alien** for tax, **student** status mainly affects **income and credits** (e.g. scholarships), not the basic **1040 vs 1040-NR** choice."
            )

    if ms in {"single", "divorced", "legally_separated", "widowed"}:
        if residency == "nonresident_alien":
            filing_parts.append(
                "Your intake shows **unmarried** for December 31; for **nonresident aliens**, **filing status** on **Form 1040** is usually **not** the right frame—use **Pub. 519**, **1040-NR**, and **8843** as applicable."
            )
        else:
            filing_parts.append(
                "Given your marital status on December 31, **Single** is typically the baseline filing status "
                "unless you qualify for **Head of household** or another special status."
            )
    elif ms == "married":
        if joint is True:
            filing_parts.append(
                "You indicated willingness to file **Married filing jointly**, which is often advantageous "
                "when spouses agree to combine income and deductions on one return."
            )
        elif joint is False:
            filing_parts.append(
                "You are not filing jointly; **Married filing separately** remains available. "
                "Depending on living arrangements and dependents, **Head of household** may still merit review."
            )
            if lived is False and valid_paths and "head_of_household" in valid_paths:
                filing_parts.append(
                    "With your answers, **Head of household** appears **on the table**—confirm details against Pub. 501 and the Code."
                )
    else:
        filing_parts.append(
            "Provide marital status on December 31 to narrow filing status. Until then, filing posture is undetermined."
        )

    if valid_paths:
        nice = ", ".join(vp.replace("_", " ") for vp in valid_paths)
        filing_parts.append(f"**Possible filing paths** from your answers include: {nice}.")

    filing_parts.append(
        "Use IRS Publication **501** (and related forms) for official filing-status rules; retrieved passages below are starting points only."
    )

    how_to_file = "\n\n".join(filing_parts) + year_bit

    # --- Deductions ---
    ded_parts: List[str] = []
    if residency == "nonresident_alien" and below_thr is True:
        ded_parts.append(
            "With **no income** (or no **1040/1040-NR** filing obligation), **Schedule A** vs. **standard deduction** is often **not** the main issue—focus first on **residency** and any required **Form 8843** per instructions."
        )
    if residency != "nonresident_alien":
        ded_parts.append(
            "Most **U.S. resident** filers choose between the **standard deduction** and **itemizing** (Schedule A). "
            "The better choice is usually whichever produces the **lower tax**."
        )
    else:
        ded_parts.append(
            "As a **nonresident alien**, deduction and form choices often follow **Form 1040-NR** rules and **Pub. 519**, "
            "not the usual resident **1040 / Schedule A** pattern."
        )
    if item_total is not None:
        try:
            itn = float(item_total)
            ded_parts.append(
                f"You gave a rough **itemized total** of ${itn:,.0f}. Compare that to the standard deduction for your filing status for {ty or 'the year'}."
            )
        except (TypeError, ValueError):
            ded_parts.append(
                "You provided an itemized deduction estimate—compare it to the standard deduction for your filing status."
            )
    else:
        ded_parts.append(
            "If you have mortgage interest, SALT, large medical expenses, or charitable gifts, estimate **itemized deductions** to compare to the standard amount."
        )

    if has_charity:
        ded_parts.append(
            "You reported **charitable contributions**. Substantiation rules (receipts, written acknowledgments) matter—especially for gifts over **$250**."
        )
        if charity_doc is True:
            ded_parts.append("You indicated documentation is in order; keep records with your tax file.")
        elif charity_doc is False:
            ded_parts.append("Without adequate records, charitable deductions may be **disallowed**—gather documentation before claiming.")

    if "deduction_documents" in active_rules and doc_req:
        ded_parts.append(
            f"**Records to gather:** {_format_doc_requirements(doc_req)}."
        )

    deductions = "\n\n".join(ded_parts)

    # --- Final report ---
    cites = _top_citations_per_call(retrieval_results)
    cite_block = "; ".join(c for c in cites if c)[:800]

    final_report = (
        "**Summary.** This companion narrowed your situation to a small set of filing and deduction themes, "
        "then pulled a **compact** set of authority excerpts (IRS publications, IRC, Tax Court) for grounding.\n\n"
        "**Not tax advice.** Verify all figures and rules against current IRS publications and the Code.\n\n"
        f"**Top citations consulted:** {cite_block or '—'}"
    )

    followups_suggested: List[str] = []
    if item_total is None and has_charity:
        followups_suggested.append("Rough total itemized deductions (if any) to compare to the standard deduction.")
    if ms == "married" and joint is False and lived is None:
        followups_suggested.append("Whether your spouse lived in your home in the last six months of the year (head-of-household path).")
    if (stu_in_us is True or visa_stu is True) and residency in (None, "", "unsure"):
        followups_suggested.append(
            "Whether you are a **resident** or **nonresident alien** for federal tax (Pub. 519)—this drives 1040 vs. 1040-NR and Form 8843."
        )
    if stu_in_us is True and visa_stu is None:
        followups_suggested.append("Whether you were in the U.S. under F-1, J-1, M-1, or similar student/exchange status (Form 8843 context).")

    report = {
        "how_to_file": how_to_file.strip(),
        "deductions": deductions.strip(),
        "final_report": final_report.strip(),
        "source_citations": cites,
        "followups_suggested": followups_suggested,
    }
    report = merge_advisory_into_report(report, facts, constraint_result)

    if use_llm is None:
        use_llm = os.environ.get("NARRATIVE_LLM", "").strip() in ("1", "true", "yes")

    if use_llm and os.environ.get("OPENAI_API_KEY", "").strip():
        enriched = _llm_summarize_sections(report, facts, retrieval_results)
        if enriched:
            report["how_to_file"] = enriched.get("how_to_file", report["how_to_file"])
            report["deductions"] = enriched.get("deductions", report["deductions"])
            report["final_report"] = enriched.get("final_report", report["final_report"])

    return report


def _llm_summarize_sections(
    draft: Dict[str, str],
    facts: Dict[str, Any],
    retrieval_results: List[Dict[str, Any]],
) -> Optional[Dict[str, str]]:
    try:
        from openai import OpenAI
    except ImportError:
        return None

    snippets: List[str] = []
    for res in retrieval_results[:6]:
        for ch in (res.get("chunks") or [])[:1]:
            snippets.append((ch.get("text") or "")[:600])

    client = OpenAI()
    prompt = (
        "You are a concise tax-education writer. Rewrite THREE sections in plain English, "
        "max 3 short paragraphs each, no markdown headers inside the strings. "
        "Do not invent facts; use only the draft and snippets.\n\n"
        f"FACTS_JSON:\n{json.dumps(facts, default=str)[:2000]}\n\n"
        f"DRAFT:\n{json.dumps(draft, indent=2)[:4000]}\n\n"
        f"SNIPPETS:\n{json.dumps(snippets, indent=2)[:6000]}\n\n"
        'Return JSON only: {"how_to_file":"...","deductions":"...","final_report":"..."}'
    )
    try:
        comp = client.chat.completions.create(
            model=os.environ.get("NARRATIVE_LLM_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = (comp.choices[0].message.content or "").strip()
        data = json.loads(raw)
        return {
            "how_to_file": str(data.get("how_to_file", "")),
            "deductions": str(data.get("deductions", "")),
            "final_report": str(data.get("final_report", "")),
        }
    except Exception:
        return None


def attach_ui_payload(plan_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Mutates/extends planning action dict with narrative + compact retrieval."""
    if plan_dict.get("action") == "retrieve":
        results = plan_dict.get("retrieval_results") or []
        plan_dict["retrieval_preview"] = _compact_retrieval_results(results)
        plan_dict["narrative_report"] = build_narrative_report(
            plan_dict.get("normalized_facts") or {},
            plan_dict.get("constraint_result") or {},
            plan_dict.get("retrieval_calls") or [],
            results,
        )
    else:
        plan_dict["retrieval_preview"] = None
        plan_dict["narrative_report"] = None
        if plan_dict.get("action") == "ask_followup":
            cr = plan_dict.get("constraint_result") or {}
            nxt: List[str] = []
            for u in cr.get("unresolved_constraints") or []:
                qh = u.get("question_hint") or u.get("reason")
                if qh:
                    nxt.append(str(qh))
            partial = {
                "how_to_file": "Complete the questions below so we can recommend a filing posture.",
                "deductions": "Deduction guidance will appear after required facts (itemized vs. standard, charitable documentation) are known.",
                "final_report": "— Awaiting your answer —",
                "source_citations": [],
                "followups_suggested": nxt[:5],
            }
            plan_dict["narrative_report"] = enrich_partial_narrative(
                partial,
                plan_dict.get("normalized_facts") or {},
                cr,
            )
    return plan_dict
