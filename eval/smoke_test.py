"""
Smoke test: verify RAGAS and HHEM work with a single hardcoded example.
Run this first to confirm your environment is set up correctly.

Usage:
    python -m eval.smoke_test              # test both RAGAS + HHEM
    python -m eval.smoke_test --hhem-only  # test HHEM only (no API key needed)
"""
import argparse
import sys


SAMPLE_QUESTION = "Who must file a tax return?"
SAMPLE_RESPONSE = (
    "According to IRS Publication 501, you must file a federal income tax return "
    "if your gross income exceeds the filing threshold for your filing status. "
    "For 2024, a single individual under 65 must file if gross income is at least $14,600."
)
SAMPLE_CONTEXT = [
    "You must file a federal income tax return if you are a citizen or resident "
    "of the United States or a resident of Puerto Rico and you meet the filing "
    "requirements for any of the following categories: Individuals in general. "
    "For 2024, you must file a return if your gross income was at least the amount "
    "shown for your filing status. Single, under 65: $14,600."
]


def test_hhem():
    print("\n--- Testing HHEM-2.1-Open ---")
    from eval.metrics.hallucination import score_hhem
    score = score_hhem(SAMPLE_CONTEXT[0], SAMPLE_RESPONSE)
    print(f"HHEM score: {score:.4f}")
    print(f"  (>{0.5} = consistent, <{0.5} = likely hallucination)")
    if score > 0.5:
        print("  PASS: response is consistent with context")
    else:
        print("  WARN: response may contain hallucinations")
    return True


def test_ragas():
    print("\n--- Testing RAGAS Faithfulness ---")
    from eval.metrics.faithfulness import score_faithfulness
    score = score_faithfulness(
        question=SAMPLE_QUESTION,
        response=SAMPLE_RESPONSE,
        contexts=SAMPLE_CONTEXT,
    )
    print(f"Faithfulness score: {score:.4f}")
    print(f"  (0-1, higher = more faithful. Target: >=0.85)")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hhem-only", action="store_true")
    args = parser.parse_args()

    print("=== Eval smoke test ===")
    print(f"Question: {SAMPLE_QUESTION}")
    print(f"Response: {SAMPLE_RESPONSE[:80]}...")

    try:
        test_hhem()
    except Exception as e:
        print(f"HHEM test failed: {e}")
        print("  Make sure transformers and torch are installed.")
        sys.exit(1)

    if not args.hhem_only:
        try:
            test_ragas()
        except Exception as e:
            print(f"RAGAS test failed: {e}")
            print("  Check GEMINI_API_KEY env var.")
            print("  Or run with --hhem-only to skip RAGAS.")
            sys.exit(1)

    print("\n=== All tests passed ===")


if __name__ == "__main__":
    main()
