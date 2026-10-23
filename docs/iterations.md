# Iterations log

Debug/adjust iterations against the real LLM (Gemini via its OpenAI-compatible endpoint). One commit per entry: what I saw in a real run, the fix, and the regression test.

## 1. Model fallback chain, quota-aware retries, per-step LLM trace
- **Observed:** First real run: the console said 'LLM=mock (fallback: RateLimitError)' yet the summary text was clearly model-written — steps were silently mixing real and mock output, and the label only reflected the last call. gemini-3-flash-preview was returning 429 quota errors.
- **Fix:** Each step goes through _ask(step, ...): models tried in order (LLM_MODEL then LLM_FALLBACK_MODELS), transient errors retried with backoff, quota 429 not retried; TRACE records per step which model answered, skipped models, tokens and latency; written to out/llm_trace.json and printed by run.py. Rerun: all 3 steps served by gemini-flash-lite-latest, with the skip visible.
- **Test:** test_trace_records_backend_per_step_and_falls_through_models

