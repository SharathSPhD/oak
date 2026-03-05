---
description: "Benchmark a model against the current default. Usage: /oak-benchmark {model_name}"
---

You are the OAK model benchmarking engine. Benchmark the model: $ARGUMENTS

## Process

1. **Verify** the model is available:
   - Check via `curl http://oak-ollama:11434/api/tags`
   - If not available, attempt to pull: `curl -X POST http://oak-ollama:11434/api/pull -d '{"name": "$ARGUMENTS"}'`

2. **Prepare** a canonical test problem:
   - Use a retail/e-commerce scenario from `manifest_domains.json`
   - Generate a small synthetic dataset (100 rows)

3. **Run** the benchmark:
   - Submit the problem twice: once with the default model (`qwen3-coder`), once with $ARGUMENTS
   - Time both executions
   - Compare: response quality (judge score), latency, token usage

4. **Report** results as:
   ```json
   {
     "model_tested": "$ARGUMENTS",
     "baseline_model": "qwen3-coder",
     "test_problem": "...",
     "results": {
       "baseline": {"score": 0.8, "latency_ms": 5000, "tokens": 1500},
       "tested": {"score": 0.85, "latency_ms": 3000, "tokens": 1200}
     },
     "recommendation": "switch|keep_current|needs_more_testing"
   }
   ```

5. Write results to `/workspaces/builder/benchmark_{model}.json`.
