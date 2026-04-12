"""
Configuration for the eval harness.
Paths, model names, and success thresholds from the eval plan.
"""
import os
from pathlib import Path

# -- load .env from repo root --
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

# -- paths --
REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = REPO_ROOT / "benchmarks"
SOURCES_DIR = REPO_ROOT / "sources"
RESULTS_DIR = REPO_ROOT / "eval" / "results"

# -- evaluator LLM --
# This is the model used to grade outputs.
# Different model family from the system LLM to avoid self-grading.
EVALUATOR_MODEL = "gpt-4o-mini"
EVALUATOR_BASE_URL = "https://api.openai.com/v1"

# -- system / baseline LLM --
# The model used for both baselines (zero-shot and given-right-sources).
SYSTEM_MODEL = "gemini-2.5-flash"
SYSTEM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# -- switching providers --
# Everything uses the OpenAI client format. To swap providers, change the
# MODEL and BASE_URL above and set the matching env var. Examples:
#
#   DeepSeek:  model="deepseek-chat", url="https://api.deepseek.com"
#   Qwen:      model="qwen3.5-plus", url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
#   Ollama:    model="qwen3:8b", url="http://localhost:11434/v1"
#   Cluster:   model="Qwen/Qwen2.5-72B-Instruct", url="http://cluster-node:8000/v1"

# -- success thresholds (from eval plan 3.3) --
THRESHOLDS = {
    "answer_correctness": 0.80,
    "constraint_accuracy_f1": 0.90,
    "faithfulness": 0.85,
    "hallucination_rate": 0.10,    # upper bound (lower is better)
    "citation_existence": 0.90,
}
