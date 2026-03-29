from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.planning.agent import PlanningAgent
from src.planning.constraint_adapter import SimpleConstraintEngine
from src.planning.contracts import RetrievalChunk, RetrievalChunkMetadata, RetrievalResponse


class MockRetrievalClient:
    """Small retrieval stub matching docs/retrieval_interface_spec.md."""

    def retrieve(self, query, source_hint=None, top_k=5, options=None):
        citation = "IRS Pub. 501, Filing Status"
        text = (
            "You may be able to file as head of household if you are considered "
            "unmarried, paid more than half the cost of keeping up a home, and "
            "had a qualifying person living with you for more than half the year."
        )
        if "charitable" in query.lower() or "records" in query.lower():
            citation = "IRS Pub. 526, Contributions"
            text = (
                "Keep written records for cash contributions and written "
                "acknowledgments for certain larger gifts."
            )

        response = RetrievalResponse(
            chunks=[
                RetrievalChunk(
                    text=text,
                    metadata=RetrievalChunkMetadata(
                        source_type=source_hint or "irs_pubs",
                        citation=citation,
                        publication_year=(options or {}).get("tax_year"),
                        page_index=1,
                    ),
                    score=0.99,
                )
            ],
            strategy="tree" if source_hint != "tax_court" else "bm25",
            sources_queried=[source_hint] if source_hint else ["irs_pubs"],
        )
        return response.to_dict()


def print_block(title, payload):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    print(json.dumps(payload, indent=2))


def main():
    agent = PlanningAgent(
        constraint_engine=SimpleConstraintEngine(),
        retrieval_client=MockRetrievalClient(),
    )

    partial_facts = {
        "tax_year": 2025,
        "marital_status_on_1231": "married",
        "spouse_willing_to_file_jointly": False,
        "has_qualifying_child": True,
        "paid_more_than_half_home_costs": True,
        "charitable_cash_contributions": 750,
    }
    first_step = agent.plan(partial_facts)
    print_block("DEMO 1: follow-up needed", first_step.to_dict())

    updated_facts = dict(partial_facts)
    updated_facts["lived_with_spouse_last_6_months"] = False
    updated_facts["charitable_contributions_documented"] = True
    updated_facts["itemized_deductions_total"] = 9000

    second_step = agent.plan(updated_facts)
    print_block("DEMO 2: retrieval ready", second_step.to_dict())


if __name__ == "__main__":
    main()
