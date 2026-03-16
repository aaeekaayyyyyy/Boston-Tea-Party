"""
Baseline runners for the vanilla LLM comparison.
Both baselines use the same model as the system to isolate the
value of RAG + constraints vs. the raw model.

Baseline A (zero-shot): no context, no constraints. Just the question.
Baseline B (given right sources): true source passages pasted into the prompt.
"""
import os
from openai import OpenAI

from eval.config import SYSTEM_MODEL, SYSTEM_BASE_URL


def _get_client() -> OpenAI:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    return OpenAI(api_key=api_key, base_url=SYSTEM_BASE_URL)


def _call_llm(messages: list[dict]) -> str:
    """Send messages to the system LLM and return the response text."""
    client = _get_client()
    response = client.chat.completions.create(
        model=SYSTEM_MODEL,
        messages=messages,
        temperature=0,
        max_tokens=4096,
    )
    return response.choices[0].message.content.strip()


# -- Baseline A: zero-shot --

ZERO_SHOT_SYSTEM = (
    "You are a tax advisor. Answer the question accurately. "
    "Cite specific IRC sections, IRS Publications, or Tax Court cases where possible."
)


def run_baseline_a(question: str) -> str:
    """Zero-shot: just the question, no context."""
    messages = [
        {"role": "system", "content": ZERO_SHOT_SYSTEM},
        {"role": "user", "content": question},
    ]
    return _call_llm(messages)


# -- Baseline B: given right sources --

CONTEXT_SYSTEM = (
    "You are a tax advisor. Answer the question using ONLY the provided source documents. "
    "Cite specific IRC sections, IRS Publications, or Tax Court cases in your answer."
)


def run_baseline_b(question: str, true_source_passages: list[dict]) -> str:
    """Given right sources: true source passages provided as context."""
    context_block = "\n\n".join(
        f"[{p['citation']}]\n{p['text']}" for p in true_source_passages
    )
    messages = [
        {"role": "system", "content": CONTEXT_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Source documents:\n{context_block}\n\n"
                f"Question: {question}"
            ),
        },
    ]
    return _call_llm(messages)


# -- batch runners --

def run_baselines(scenarios: list[dict]) -> list[dict]:
    """
    Run both baselines on a list of scenarios.
    Returns list of dicts with keys: id, question, baseline_a_response, baseline_b_response.
    Skips Baseline B if true_source_passages is missing.
    """
    results = []
    for s in scenarios:
        print(f"  Running baselines for {s['id']}...")
        result = {
            "id": s["id"],
            "question": s["question"],
            "true_answer": s["answer"],
            "baseline_a_response": run_baseline_a(s["question"]),
        }
        if s.get("true_source_passages"):
            result["baseline_b_response"] = run_baseline_b(
                s["question"], s["true_source_passages"]
            )
        else:
            result["baseline_b_response"] = None
            print(f"    Skipped Baseline B for {s['id']} (no true_source_passages)")
        results.append(result)
    return results
