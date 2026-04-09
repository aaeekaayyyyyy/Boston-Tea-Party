from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .contracts import (
    ConstraintEngineProtocol,
    PlanningAction,
    RetrievalClientProtocol,
    UnresolvedConstraint,
)
from .intake import merge_fact_updates, normalize_user_facts


# Planner → retrieval: IRC section priors aligned with SimpleConstraintEngine rules (Jonathan scenarios).
RULE_RETRIEVAL_OPTIONS: Dict[str, Dict[str, Any]] = {
    "filing_status": {
        "irs_publication": "501",
        # Order matters for IRC priors: marital-status definition before general filing-status rules.
        "irc_sections_hint": ["7703", "2", "1", "152"],
    },
    "standard_deduction": {
        "irs_publication": "501",
        "irc_sections_hint": ["63", "68", "151"],
    },
    "deduction_documents": {
        "irs_publication": "526",
        "irc_sections_hint": ["170"],
    },
    "nonresident_student": {
        "irs_publication": "519",
        "irc_sections_hint": ["7701", "871", "873"],
    },
}


def _should_retrieve_pub519(facts: Dict[str, Any]) -> bool:
    """Extra retrieval when student / NRA context—8843 and Pub. 519."""
    res = facts.get("federal_tax_residency")
    if isinstance(res, str):
        res = res.strip().lower().replace(" ", "_")
    stu = facts.get("is_student_in_us")
    visa = facts.get("us_student_visa_f1_j1_m")
    if res == "nonresident_alien" and (stu is True or visa is True):
        return True
    if visa is True:
        return True
    if stu is True and res in (None, "", "unsure"):
        return True
    return False


QUESTION_TEMPLATES = {
    "marital_status_on_1231": "What was your marital status on December 31 of the tax year?",
    "spouse_willing_to_file_jointly": "Are you and your spouse planning to file jointly?",
    "lived_with_spouse_last_6_months": (
        "Did your spouse live in your home during the last 6 months of the tax year?"
    ),
    "has_qualifying_child": "Did you have a qualifying child for the year?",
    "paid_more_than_half_home_costs": (
        "Did you pay more than half the cost of keeping up the home for the year?"
    ),
    "itemized_deductions_total": (
        "Do you know the rough total of your itemized deductions for the year?"
    ),
    "charitable_contributions_documented": (
        "Do you already have receipts or written acknowledgments for your charitable contributions?"
    ),
}


class PlanningAgent:
    """
    Planning agent v1
    1. Ask the single highest-priority follow-up question when facts are missing.
    2. Build retrieval calls once the facts are sufficient.
    """

    def __init__(
        self,
        constraint_engine: ConstraintEngineProtocol,
        retrieval_client: Optional[RetrievalClientProtocol] = None,
    ) -> None:
        self.constraint_engine = constraint_engine
        self.retrieval_client = retrieval_client

    def plan(self, facts: Dict[str, Any]) -> PlanningAction:
        normalized_facts = normalize_user_facts(facts)
        constraint_result = self.constraint_engine.evaluate(normalized_facts)

        if constraint_result.unresolved_constraints:
            chosen = self._pick_constraint(constraint_result.unresolved_constraints)
            question = self._question_for(chosen)

            return PlanningAction(
                action="ask_followup",
                message="More information is needed before retrieval.",
                target_field=chosen.field,
                reason=chosen.reason,
                question=question,
                normalized_facts=normalized_facts,
                constraint_result=constraint_result.to_dict(),
            )

        retrieval_calls = self._build_retrieval_calls(
            normalized_facts,
            constraint_result.active_rules,
            constraint_result.explanation_goals,
        )

        retrieval_results: List[Dict[str, Any]] = []
        if self.retrieval_client is not None:
            for call in retrieval_calls:
                retrieval_results.append(self.retrieval_client.retrieve(**call))

        return PlanningAction(
            action="retrieve",
            message="Facts are sufficient to retrieve supporting authority.",
            retrieval_calls=retrieval_calls,
            retrieval_results=retrieval_results,
            normalized_facts=normalized_facts,
            constraint_result=constraint_result.to_dict(),
        )

    def replan(self, current_facts: Dict[str, Any], updates: Dict[str, Any]) -> PlanningAction:
        merged = merge_fact_updates(current_facts, updates)
        return self.plan(merged)

    def _pick_constraint(self, constraints: List[UnresolvedConstraint]) -> UnresolvedConstraint:
        return sorted(constraints, key=lambda item: item.priority)[0]

    def _question_for(self, constraint: UnresolvedConstraint) -> str:
        if constraint.question_hint:
            return constraint.question_hint
        return QUESTION_TEMPLATES.get(
            constraint.field,
            f"Can you clarify `{constraint.field}`?",
        )

    def _retrieval_options(
        self,
        facts: Dict[str, Any],
        active_rules: Sequence[str],
        rule_id: str,
    ) -> Dict[str, Any]:
        tax_year = facts.get("tax_year")
        opts: Dict[str, Any] = {
            "tax_year": tax_year,
            "active_rules": list(active_rules),
            "rule_id": rule_id,
        }
        extra = RULE_RETRIEVAL_OPTIONS.get(rule_id)
        if extra:
            opts.update(extra)
        return opts

    def _build_retrieval_calls(
        self,
        facts: Dict[str, Any],
        active_rules: List[str],
        explanation_goals: List[str],
    ) -> List[Dict[str, Any]]:
        calls: List[Dict[str, Any]] = []
        ar = list(active_rules)

        if _should_retrieve_pub519(facts):
            calls.append(
                {
                    "query": (
                        "IRS Publication 519 nonresident alien student Form 8843 exempt individual "
                        "substantial presence F-1 J-1 filing requirement"
                    ),
                    "source_hint": "irs_pubs",
                    "top_k": 5,
                    "options": self._retrieval_options(facts, ar, "nonresident_student"),
                }
            )

        if "filing_status" in active_rules:
            q = self._filing_status_query(facts)
            calls.append(
                {
                    "query": q,
                    "source_hint": "irs_pubs",
                    "top_k": 5,
                    "options": self._retrieval_options(facts, ar, "filing_status"),
                }
            )
            calls.append(
                {
                    "query": q + " 26 USC marital status qualifying child",
                    "source_hint": "irc",
                    "top_k": 4,
                    "options": self._retrieval_options(facts, ar, "filing_status"),
                }
            )

        if "standard_deduction" in active_rules:
            calls.append(
                {
                    "query": "When should a taxpayer take the standard deduction instead of itemizing?",
                    "source_hint": "irs_pubs",
                    "top_k": 5,
                    "options": self._retrieval_options(facts, ar, "standard_deduction"),
                }
            )
            calls.append(
                {
                    "query": "standard deduction amount and limitations Internal Revenue Code",
                    "source_hint": "irc",
                    "top_k": 4,
                    "options": self._retrieval_options(facts, ar, "standard_deduction"),
                }
            )

        if "deduction_documents" in active_rules:
            calls.append(
                {
                    "query": "What records are required for charitable contribution deductions?",
                    "source_hint": "irs_pubs",
                    "top_k": 5,
                    "options": self._retrieval_options(facts, ar, "deduction_documents"),
                }
            )
            calls.append(
                {
                    "query": "charitable contribution substantiation section 170 Tax Court",
                    "source_hint": "tax_court",
                    "top_k": 3,
                    "options": self._retrieval_options(facts, ar, "deduction_documents"),
                }
            )

        if not calls:
            # Fallback to one general request so the planner still does something useful.
            goal_text = explanation_goals[0] if explanation_goals else "Explain the relevant tax rules."
            calls.append(
                {
                    "query": goal_text,
                    "source_hint": None,
                    "top_k": 5,
                    "options": {
                        "tax_year": facts.get("tax_year"),
                        "active_rules": ar,
                        "rule_id": None,
                    },
                }
            )

        return calls

    def _filing_status_query(self, facts: Dict[str, Any]) -> str:
        marital_status = facts.get("marital_status_on_1231")

        if marital_status == "married":
            if facts.get("paid_more_than_half_home_costs") and (
                facts.get("has_qualifying_child") or facts.get("has_other_qualifying_persons")
            ):
                return "Who qualifies for head of household filing status when married but living apart?"
            if facts.get("spouse_willing_to_file_jointly"):
                return "What are the rules for married filing jointly?"
            return "What are the filing status options for a married taxpayer?"

        if marital_status in {"single", "divorced", "legally_separated", "widowed"}:
            return (
                "IRS Publication 501 filing status rules for single unmarried taxpayer "
                "head of household qualifying surviving spouse"
            )

        return "What filing status rules apply in this scenario?"
