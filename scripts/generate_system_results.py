"""
Generate system responses for eval scoring.
For each benchmark scenario: retrieve real chunks, send to LLM, save output.

Usage:
    python scripts/generate_system_results.py
    python scripts/generate_system_results.py --source-hint auto
    python scripts/generate_system_results.py --dry-run

Then score with:
    python -m eval.harness --system-results eval/results/system_outputs.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.config import SYSTEM_MODEL, SYSTEM_BASE_URL
from eval.loader import load_all_scenarios
from src.rag.client import HybridRetrievalClient


# Must match baselines.py CONTEXT_SYSTEM exactly
SYSTEM_PROMPT = (
    "You are a tax advisor. Answer the question using ONLY the provided source documents. "
    "Cite specific IRC sections, IRS Publications, or Tax Court cases in your answer."
)


def _get_llm_client():
    from openai import OpenAI
    api_key = os.environ.get("GEMINI_API_KEY", "")
    return OpenAI(api_key=api_key, base_url=SYSTEM_BASE_URL)


def _generate_response(question: str, chunks: list[dict]) -> str:
    """Send retrieved chunks + question to the LLM and return the answer."""
    if not chunks:
        return ""

    context_block = "\n\n".join(
        f"[{c['metadata']['citation']}]\n{c['text']}" for c in chunks
    )
    client = _get_llm_client()
    result = client.chat.completions.create(
        model=SYSTEM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Source documents:\n{context_block}\n\nQuestion: {question}"},
        ],
        temperature=0,
        max_tokens=4096,
    )
    return result.choices[0].message.content.strip()


def _pick_source_hint(scenario: dict) -> str | None:
    """Infer source_hint from the scenario's source_type field."""
    st = scenario.get("source_type", "")
    if st == "irc":
        return "irc"
    if st in ("irs_pubs", "irs_pub"):
        return "irs_pubs"
    if st == "tax_court":
        return "tax_court"
    return None  # auto-route


def run(
    source_hint_override: str | None = None,
    dry_run: bool = False,
    top_k: int = 5,
) -> list[dict]:
    """Generate system results for all baseline-scorable scenarios."""
    all_scenarios = load_all_scenarios()

    # Same filter as the harness baseline path
    BASELINE_TYPES = {"factual_lookup", "eligibility_determination", "calculation", None}
    scenarios = [s for s in all_scenarios if s.get("question_type") in BASELINE_TYPES]
    print(f"Generating system results for {len(scenarios)} scenarios")

    retrieval_client = HybridRetrievalClient(repo_root=ROOT)
    results = []

    for s in scenarios:
        sid = s["id"]
        question = s["question"]
        hint = source_hint_override or _pick_source_hint(s)

        print(f"  {sid}: retrieving (hint={hint})...", end="", flush=True)
        resp = retrieval_client.retrieve(query=question, source_hint=hint, top_k=top_k)
        chunks = resp.get("chunks", [])
        print(f" {len(chunks)} chunks", end="", flush=True)

        if dry_run:
            response_text = None
            print(" [dry-run, skipping LLM]")
        else:
            print(" -> LLM...", end="", flush=True)
            response_text = _generate_response(question, chunks)
            print(f" {len(response_text)} chars")

        results.append({
            "id": sid,
            "system_output": {
                "action": "retrieve",
                "retrieval_calls": [{"query": question, "source_hint": hint, "top_k": top_k}],
                "retrieval_results": [resp],
                "constraint_result": {},
            },
            "response": response_text,
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="Generate system results for eval")
    parser.add_argument("--source-hint", type=str, default=None,
                        help="Override source_hint for all queries (irs_pubs, irc, tax_court, or auto)")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve")
    parser.add_argument("--dry-run", action="store_true", help="Retrieve only, skip LLM calls")
    args = parser.parse_args()

    hint = None if args.source_hint == "auto" else args.source_hint
    results = run(source_hint_override=hint, dry_run=args.dry_run, top_k=args.top_k)

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"system_outputs_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")
    print(f"Score with: python -m eval.harness --system-results {out_path}")


if __name__ == "__main__":
    main()
