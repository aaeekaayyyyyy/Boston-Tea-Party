from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.planning.agent import PlanningAgent
from src.planning.constraint_adapter import SimpleConstraintEngine


class SilentMockRetrieval:
    def retrieve(self, query, source_hint=None, top_k=5, options=None):
        return {
            "chunks": [],
            "strategy": "tree" if source_hint != "tax_court" else "bm25",
            "sources_queried": [source_hint] if source_hint else [],
            "retrieval_empty": True,
            "retrieval_message": "mock: no chunks",
        }


def run_case_1(agent: PlanningAgent) -> None:
    facts = {
        "tax_year": 2025,
        "marital_status_on_1231": "married",
        "spouse_willing_to_file_jointly": False,
        "has_qualifying_child": True,
        "paid_more_than_half_home_costs": True,
    }
    action = agent.plan(facts)
    assert action.action == "ask_followup"
    assert action.target_field == "lived_with_spouse_last_6_months"


def run_case_2(agent: PlanningAgent) -> None:
    facts = {
        "tax_year": 2025,
        "marital_status_on_1231": "married",
        "spouse_willing_to_file_jointly": False,
        "lived_with_spouse_last_6_months": False,
        "has_qualifying_child": True,
        "paid_more_than_half_home_costs": True,
        "charitable_cash_contributions": 500,
        "charitable_contributions_documented": True,
        "itemized_deductions_total": 9000,
    }
    action = agent.plan(facts)
    assert action.action == "retrieve"
    assert len(action.retrieval_calls) >= 1


def main() -> None:
    agent = PlanningAgent(SimpleConstraintEngine(), SilentMockRetrieval())
    run_case_1(agent)
    run_case_2(agent)
    print("planning_smoke_test: ok")


if __name__ == "__main__":
    main()
