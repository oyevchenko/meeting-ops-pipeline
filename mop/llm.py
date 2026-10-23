"""Pluggable LLM: real OpenAI-compatible API by default when OPENAI_API_KEY or GEMINI_API_KEY is set
(Gemini via its OpenAI-compatible endpoint); deterministic mock when LLM_MODE=mock or no key."""
import json, os, re, time

TRACE: list[dict] = []  # one row per pipeline step: which backend actually answered, tokens, latency

def _client():
    if os.getenv("LLM_MODE") == "mock": return None
    key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key: return None
    from openai import OpenAI
    gem = not os.getenv("OPENAI_API_KEY")
    base = os.getenv("OPENAI_BASE_URL") or ("https://generativelanguage.googleapis.com/v1beta/openai/" if gem else None)
    models = [os.getenv("LLM_MODEL", "gemini-3-flash-preview" if gem else "gpt-4o-mini")]
    models += [m for m in os.getenv("LLM_FALLBACK_MODELS", "gemini-flash-lite-latest,gemini-3.5-flash" if gem else "").split(",") if m]
    return OpenAI(api_key=key, base_url=base, timeout=60, max_retries=0), models

def _create(cli, model, prompt, attempts=3, sleep=time.sleep):
    import openai
    for i in range(attempts):
        try:
            return cli.chat.completions.create(model=model, temperature=0, response_format={"type": "json_object"},
                                               messages=[{"role": "user", "content": prompt}])
        except (openai.InternalServerError, openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError) as e:
            if i == attempts - 1 or "quota" in str(e).lower(): raise
            sleep(2 ** i)

def _ask(step, prompt, fallback):
    c, t0 = _client(), time.time()
    if c:
        cli, models = c
        errors = []
        for model in models:
            try:
                r = _create(cli, model, prompt)
                out = json.loads(r.choices[0].message.content)
                u = r.usage
                TRACE.append({"step": step, "backend": model, "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
                              "latency_ms": round((time.time() - t0) * 1000), "errors": errors})
                return out
            except Exception as e:
                errors.append(f"{model}: {type(e).__name__}")
        TRACE.append({"step": step, "backend": "mock (fallback)", "errors": errors})
        return fallback()
    TRACE.append({"step": step, "backend": "mock", "errors": []})
    return fallback()

def backends() -> str:
    return ", ".join(sorted({t["backend"] for t in TRACE}))

AI_RE = re.compile(r"- \[( |x)\] @([^:]+):\s*(.+?)\s+—\s+due\s+(\d{4}-\d{2}-\d{2})")

def summarize(meeting):
    md = meeting["notes_markdown"]
    def mock():
        sec = lambda h: re.search(rf"## {h}\n(.+?)(\n## |\Z)", md, re.S).group(1).strip()
        return {"tldr": sec("Summary").split("\n")[0], "decisions": [l[2:] for l in sec("Decisions").splitlines()]}
    return _ask("summarize", f"Summarize as JSON {{tldr, decisions[]}}:\n{md}", mock)

def extract_action_items(meeting):
    def mock():
        return {"items": [{"owner": o.strip(), "title": t, "due": d, "done": x == "x"} for x, o, t, d in AI_RE.findall(meeting["notes_markdown"])]}
    return _ask("extract_action_items", f"Extract action items as JSON {{items:[{{owner,title,due,done}}]}}:\n{meeting['notes_markdown']}", mock)["items"]

def closing_report(meeting, items, today):
    def mock():
        slips = [i for i in items if i["completed_on"] > i["due"]]
        lines = [f"- {i['title']} — {i['owner']}, due {i['due']}, done {i['completed_on']}" + (" (slipped)" if i in slips else "") for i in items]
        return {"subject": f"[Closed] {meeting['title']} — all {len(items)} action items done",
                "body": f"Hi all,\n\nAll action items from \"{meeting['title']}\" ({meeting['date']}) are complete as of {today}.\n\n"
                        + "\n".join(lines) + f"\n\nSlips: {len(slips)}" + (" — " + ", ".join(s['title'] for s in slips) if slips else " — none")
                        + ".\n\nThanks everyone,\nOleksii", "slips": len(slips)}
    return _ask("closing_report", f"Write a closing report JSON {{subject, body, slips}} for: {json.dumps(items)}", mock)
