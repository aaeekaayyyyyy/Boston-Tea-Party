"""
Hallucination detection using HHEM-2.1-Open (Vectara).
Standalone usage outside of RAGAS - gives a factual consistency score per (context, response) pair.
Runs locally, no API key needed. ~600MB model, ~1.5s per pair on CPU.

HHEM is built on T5, so we load the T5 tokenizer explicitly since
AutoTokenizer doesn't recognize HHEM's custom config class.
"""
import torch

_model = None
_tokenizer = None


def _load_model():
    """Lazy-load HHEM-2.1-Open from HuggingFace."""
    global _model, _tokenizer
    if _model is None:
        from transformers import AutoModelForSequenceClassification, T5Tokenizer

        model_name = "vectara/hallucination_evaluation_model"
        print(f"Loading {model_name} (first time may download ~600MB)...")
        _tokenizer = T5Tokenizer.from_pretrained("t5-base")
        _model = AutoModelForSequenceClassification.from_pretrained(
            model_name, trust_remote_code=True
        )
        _model.eval()
        print("HHEM loaded.")
    return _model, _tokenizer


def score_hhem(premise: str, hypothesis: str) -> float:
    """
    Score factual consistency of hypothesis given premise.

    Args:
        premise: the source/context text (evidence)
        hypothesis: the generated text to check

    Returns:
        float 0-1. Higher = more consistent with premise. <0.5 = likely hallucination.
    """
    model, tokenizer = _load_model()
    inputs = tokenizer(
        premise,
        hypothesis,
        return_tensors="pt",
        truncation=True,
        max_length=2048,
        padding=True,
    )
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.softmax(logits, dim=-1)
        # HHEM outputs 2 classes.
        # Index 0 = hallucinated, Index 1 = consistent (verified by checking
        # that grounded responses get higher scores at index 1).
        score = probs[0][1].item()
    return score


def score_hhem_batch(pairs: list[dict]) -> list[float]:
    """
    Score multiple (premise, hypothesis) pairs.
    Each dict must have keys: premise, hypothesis.
    """
    return [score_hhem(p["premise"], p["hypothesis"]) for p in pairs]
