"""
Hallucination detection using LettuceDetect.
Token-level span detection built on ModernBERT. Identifies the exact words
in a response that are unsupported by context.

This is the primary hallucination detector (replaces HHEM as the Week 2 stopgap).
Runs locally, no API key needed. ~396M params (large) or ~150M params (base).

Usage:
    from eval.metrics.lettucedetect_metric import score_lettucedetect
    result = score_lettucedetect(contexts, question, answer)
    # result = {
    #     "hallucination_rate": 0.12,     # fraction of answer that's hallucinated (0-1)
    #     "has_hallucinations": True,      # any spans flagged?
    #     "hallucinated_spans": [          # exact text that's unsupported
    #         {"text": "69 million", "start": 45, "end": 55, "confidence": 0.99}
    #     ],
    #     "n_spans": 1,
    # }
"""

_detector = None


def _load_detector(use_large: bool = True):
    """Lazy-load the LettuceDetect model."""
    global _detector
    if _detector is None:
        from lettucedetect.models.inference import HallucinationDetector

        if use_large:
            model_path = "KRLabsOrg/lettucedect-large-modernbert-en-v1"
        else:
            model_path = "KRLabsOrg/lettucedect-base-modernbert-en-v1"

        print(f"Loading LettuceDetect ({model_path})...")
        _detector = HallucinationDetector(
            method="transformer",
            model_path=model_path,
        )
        print("LettuceDetect loaded.")
    return _detector


def score_lettucedetect(
    contexts: list[str],
    question: str,
    answer: str,
    use_large: bool = True,
) -> dict:
    """
    Detect hallucinated spans in the answer given context and question.

    Args:
        contexts: list of context/source passages
        question: the user's question
        answer: the generated response to check
        use_large: if True, use the large model (396M, 79.2% F1).
                   if False, use the base model (150M, faster but less accurate).

    Returns:
        dict with:
            hallucination_rate: float 0-1, fraction of answer characters in hallucinated spans
            has_hallucinations: bool, whether any spans were flagged
            hallucinated_spans: list of span dicts with text, start, end, confidence
            n_spans: int, number of hallucinated spans detected
    """
    detector = _load_detector(use_large=use_large)

    # Get span-level predictions
    spans = detector.predict(
        context=contexts,
        question=question,
        answer=answer,
        output_format="spans",
    )

    # Compute hallucination rate as fraction of answer characters that are hallucinated
    answer_len = len(answer)
    if answer_len == 0:
        return {
            "hallucination_rate": 0.0,
            "has_hallucinations": False,
            "hallucinated_spans": [],
            "n_spans": 0,
        }

    hallucinated_chars = sum(span["end"] - span["start"] for span in spans)
    hallucination_rate = min(hallucinated_chars / answer_len, 1.0)

    return {
        "hallucination_rate": hallucination_rate,
        "has_hallucinations": len(spans) > 0,
        "hallucinated_spans": [
            {
                "text": span["text"],
                "start": span["start"],
                "end": span["end"],
                "confidence": span["confidence"],
            }
            for span in spans
        ],
        "n_spans": len(spans),
    }
