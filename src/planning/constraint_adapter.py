from __future__ import annotations

from typing import Any, Dict, List

from .contracts import ConstraintResult, UnresolvedConstraint
from .intake import has_any_charitable_contribution


class SimpleConstraintEngine:
    """
    Simple version of John's rule engine.
    """

    def evaluate(self, facts: Dict[str, Any]) -> ConstraintResult:
        unresolved: List[UnresolvedConstraint] = []
        active_rules: List[str] = []
        explanation_goals: List[str] = []
        valid_paths: List[str] = []
        documentation_requirements: List[str] = []

        marital_status = facts.get("marital_status_on_1231")
        spouse_joint = facts.get("spouse_willing_to_file_jointly")
        lived_apart = facts.get("lived_with_spouse_last_6_months")
        paid_home_costs = facts.get("paid_more_than_half_home_costs")
        has_child = facts.get("has_qualifying_child")
        other_person = facts.get("has_other_qualifying_persons")
        itemized_total = facts.get("itemized_deductions_total")
        itemized_exceeds = facts.get("itemized_deductions_exceed_standard")
        charity_documented = facts.get("charitable_contributions_documented")

        # Filing-status planning
        active_rules.append("filing_status")

        if marital_status is None:
            unresolved.append(
                UnresolvedConstraint(
                    constraint_id="C-FILING-001",
                    field="marital_status_on_1231",
                    reason="Filing status analysis starts with your marital status on December 31.",
                    priority=1,
                    question_hint="What was your marital status on December 31 of the tax year?",
                    source_hint="irs_pubs",
                )
            )
        else:
            if marital_status in {"single", "divorced", "separated", "widowed", "legally_separated"}:
                valid_paths.append("single")

            if marital_status == "married":
                valid_paths.append("married_filing_separately")

                if spouse_joint is None:
                    unresolved.append(
                        UnresolvedConstraint(
                            constraint_id="C-FILING-002",
                            field="spouse_willing_to_file_jointly",
                            reason="Joint filing determines whether the married filing jointly path is open.",
                            priority=2,
                            question_hint="Are you and your spouse planning to file jointly?",
                            source_hint="irs_pubs",
                        )
                    )
                elif spouse_joint:
                    valid_paths.append("married_filing_jointly")

                # Head of household path is worth checking for married taxpayers who lived apart.
                if lived_apart is None:
                    unresolved.append(
                        UnresolvedConstraint(
                            constraint_id="C-FILING-003",
                            field="lived_with_spouse_last_6_months",
                            reason="Living apart for the last 6 months can affect head of household eligibility.",
                            priority=3,
                            question_hint="Did your spouse live in your home during the last 6 months of the tax year?",
                            source_hint="irs_pubs",
                        )
                    )
                elif lived_apart is False:
                    # False here means the spouse did NOT live in the home during the last 6 months
                    if has_child is None and other_person is None:
                        unresolved.append(
                            UnresolvedConstraint(
                                constraint_id="C-FILING-004",
                                field="has_qualifying_child",
                                reason="A qualifying person is needed to evaluate head of household.",
                                priority=4,
                                question_hint="Did you have a qualifying child or other qualifying person living with you?",
                                source_hint="irs_pubs",
                            )
                        )
                    if paid_home_costs is None:
                        unresolved.append(
                            UnresolvedConstraint(
                                constraint_id="C-FILING-005",
                                field="paid_more_than_half_home_costs",
                                reason="Head of household requires paying more than half the cost of keeping up the home.",
                                priority=5,
                                question_hint="Did you pay more than half the cost of keeping up the home for the year?",
                                source_hint="irs_pubs",
                            )
                        )
                    if paid_home_costs is True and (has_child is True or other_person is True):
                        valid_paths.append("head_of_household")

        explanation_goals.append("Explain likely filing status options.")

        # Deduction planning
        active_rules.append("standard_deduction")
        if itemized_exceeds is None:
            has_itemized_signals = any(
                (facts.get("medical_expenses_paid"), facts.get("mortgage_interest_paid"),
                 facts.get("real_estate_taxes_paid"), facts.get("state_local_income_tax_paid"),
                 facts.get("state_local_sales_tax_paid"))
            ) or has_any_charitable_contribution(facts)

            if has_itemized_signals and itemized_total is None:
                unresolved.append(
                    UnresolvedConstraint(
                        constraint_id="C-DED-001",
                        field="itemized_deductions_total",
                        reason="We need a rough itemized deduction total to compare itemizing against the standard deduction.",
                        priority=6,
                        question_hint="Do you know the rough total of your itemized deductions for the year?",
                        source_hint="irs_pubs",
                    )
                )

        explanation_goals.append("Explain whether standard deduction or itemizing looks more likely.")

        # Documentation planning
        if has_any_charitable_contribution(facts):
            active_rules.append("deduction_documents")
            documentation_requirements.append("charitable_acknowledgments")
            if charity_documented is None:
                unresolved.append(
                    UnresolvedConstraint(
                        constraint_id="C-DOC-001",
                        field="charitable_contributions_documented",
                        reason="Charitable deductions depend on having the right records or acknowledgments.",
                        priority=7,
                        question_hint="Do you already have receipts or written acknowledgments for your charitable contributions?",
                        source_hint="irs_pubs",
                    )
                )

        unresolved.sort(key=lambda item: item.priority)

        status = "answerable"
        if any(item.blocking for item in unresolved):
            status = "needs_more_info"

        return ConstraintResult(
            status=status,
            active_rules=active_rules,
            unresolved_constraints=unresolved,
            explanation_goals=explanation_goals,
            valid_paths=valid_paths,
            invalid_paths=[],
            documentation_requirements=documentation_requirements,
        )
