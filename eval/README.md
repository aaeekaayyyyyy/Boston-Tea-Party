# Eval Harness

Evaluation framework for Boston Tea Party 2.0.

## Quick start

```bash
pip install -r requirements.txt

# Local metric smoke check (LettuceDetect + legacy HHEM, no API key needed)
python -m eval.smoke_test --hhem-only

# Full smoke test (needs GEMINI_API_KEY)
export GEMINI_API_KEY=your-key
python -m eval.smoke_test

# Standalone rule benchmark (separate from answer-generation eval)
python -m eval.constraint_benchmark

# Run eval (uses LettuceDetect for hallucination)
python -m eval.harness

# Legacy compatibility flag: skip faithfulness/API calls
python -m eval.harness --hhem-only

# Dry run (load scenarios only)
python -m eval.harness --dry-run
```

The harness now uses LettuceDetect as its hallucination metric. The retained
`--hhem-only` flag is only a compatibility shortcut for running the local-only
subset without faithfulness/API calls.

`python -m eval.constraint_benchmark` is a separate standalone rule-benchmark
path for scoring the YAML rule benchmarks under `src/benchmarks/`. It does not
run the answer-generation harness.

## Environment variables

Add to `.env` in repo root:

```
GEMINI_API_KEY=AIza...
```

## Switching providers

Everything uses the OpenAI client format. Swap = change config.py:

- Gemini (free): model=gemini-2.5-flash, url=generativelanguage.googleapis.com/v1beta/openai/
- DeepSeek ($0.28/M): model=deepseek-chat, url=api.deepseek.com
- Qwen ($0.26/M): model=qwen3.5-plus, url=dashscope-intl.aliyuncs.com/compatible-mode/v1
- Ollama (free, local): model=qwen3:8b, url=localhost:11434/v1
- Cluster vLLM (free): model=Qwen/Qwen2.5-72B-Instruct, url=cluster-node:8000/v1

## Adding scenarios

Put JSON files in benchmarks/. Minimum fields per scenario:

```json
{
  "id": "TC-001",
  "question": "...",
  "answer": "...",
  "required_citations": ["..."],
  "constraint_result": { "eligible": true, "conditions_met": ["..."] }
}
```

See docs/benchmark_schema.md for full spec.
