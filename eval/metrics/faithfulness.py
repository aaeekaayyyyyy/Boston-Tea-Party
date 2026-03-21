"""
RAGAS Faithfulness metric wrapper.
Supports both the standard LLM-judge approach and the HHEM variant.
"""
import asyncio
import os

from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import Faithfulness, FaithfulnesswithHHEM


def _get_evaluator_llm():
    """Build the RAGAS evaluator LLM from config."""
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from eval.config import EVALUATOR_MODEL, EVALUATOR_BASE_URL

    api_key = os.environ.get("GEMINI_API_KEY", "")
    client = AsyncOpenAI(api_key=api_key, base_url=EVALUATOR_BASE_URL)
    # Raise max_tokens well above the default — RAGAS uses instructor internally
    # to parse structured outputs, and the default cap causes finish_reason='length'
    # which makes instructor retry and eventually throw InstructorRetryException.
    return llm_factory(EVALUATOR_MODEL, client=client, max_tokens=8192)


def score_faithfulness(
    question: str,
    response: str,
    contexts: list[str],
    use_hhem: bool = False,
) -> float:
    """
    Score faithfulness of a response against retrieved contexts.

    Args:
        question: the user's question
        response: the system's generated answer
        contexts: list of context passages (from retrieval or true sources)
        use_hhem: if True, use HHEM-2.1-Open for claim verification (free, no API).
                  if False, use the evaluator LLM (DeepSeek, costs a few cents).

    Returns:
        float 0-1, fraction of claims supported by context.
    """
    sample = SingleTurnSample(
        user_input=question,
        response=response,
        retrieved_contexts=contexts,
    )

    if use_hhem:
        # Uses Vectara HHEM-2.1-Open locally for the verification step.
        # Still needs an LLM for claim decomposition.
        llm = _get_evaluator_llm()
        scorer = FaithfulnesswithHHEM(llm=llm)
    else:
        llm = _get_evaluator_llm()
        scorer = Faithfulness(llm=llm)

    result = asyncio.run(scorer.single_turn_ascore(sample))
    return float(result)


def score_faithfulness_batch(
    samples: list[dict],
    use_hhem: bool = False,
) -> list[float]:
    """
    Score faithfulness for multiple samples.
    Each sample dict must have keys: question, response, contexts.

    Returns list of floats, one per sample.
    """
    return [
        score_faithfulness(
            question=s["question"],
            response=s["response"],
            contexts=s["contexts"],
            use_hhem=use_hhem,
        )
        for s in samples
    ]
