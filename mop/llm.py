"""Pluggable LLM: real OpenAI-compatible API by default when OPENAI_API_KEY or GEMINI_API_KEY is set
(Gemini via its OpenAI-compatible endpoint); deterministic mock when LLM_MODE=mock or no key."""
import json, os, re, time
from datetime import date
from .dates import resolve

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

def _ask(step, prompt, fallback, validate=None):
    c, t0 = _client(), time.time()
    if c:
        cli, models = c
        errors = []
        for model in models:
            try:
                r = _create(cli, model, prompt)
                out = json.loads(r.choices[0].message.content)
                if validate and (problems := validate(out)):  # one corrective re-ask on the same model
                    r = _create(cli, model, prompt + f"\n\nYour previous answer had problems: {problems}. Fix them and return JSON only.")
                    out = json.loads(r.choices[0].message.content)
                    if validate(out):
                        raise ValueError(f"invalid output after re-ask: {validate(out)}")
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
        def sec(h):  # notes from Notion AI don't always have every section
            m = re.search(rf"## {h}\n(.+?)(\n## |\Z)", md, re.S)
            return m.group(1).strip() if m else ""
        return {"tldr": (sec("Summary") or md.strip()).split("\n")[0], "decisions": [l[2:] for l in sec("Decisions").splitlines() if l.startswith("- ")]}
    return _ask("summarize", f"Summarize as JSON {{tldr, decisions[]}}:\n{md}", mock)

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _check_items(o):
    items = o.get("items")
    if not isinstance(items, list): return ["'items' must be a list"]
    bad = [i.get("due") for i in items if i.get("due") is not None and not (isinstance(i.get("due"), str) and ISO.match(i["due"]))]
    return [f"due must be YYYY-MM-DD or null, got: {bad}"] if bad else []

def extract_action_items(meeting):
    d = date.fromisoformat(meeting["date"])
    def mock():
        return {"items": [{"owner": o.strip(), "title": t, "due": dd, "due_raw": dd, "done": x == "x"} for x, o, t, dd in AI_RE.findall(meeting["notes_markdown"])]}
    prompt = (f"Meeting date: {d.isoformat()} ({d.strftime('%A')}). Extract every action item from the notes (any language; keep titles in the "
              "original language). Merge duplicates that describe the same task for the same person. Return JSON "
              "{items:[{owner, title, due, due_raw, done}]}. owner = the name exactly as written, or null if nobody was assigned. "
              "due_raw = the deadline text exactly as written (or null). due = that deadline resolved to YYYY-MM-DD relative to the meeting date: "
              "'next <weekday>' / 'до наступної <день>' = that weekday in the following calendar week; 'end of (next) week' = Friday of that week; "
              "'до понеділка' / 'by Monday' = the next Monday; 'ASAP'/'терміново' = next business day; a bare day+month = that date in the "
              "meeting's year (or next year if already passed). due = null if there is no deadline.\n\n" + meeting["notes_markdown"])
    items = _ask("extract_action_items", prompt, mock, validate=_check_items)["items"]
    out = []
    for i in items:
        det = resolve(i.get("due_raw"), d)
        src = "rule" if det else ("llm" if i.get("due") else None)
        out.append({**i, "due": det.isoformat() if det else i.get("due"), "due_source": src, "done": bool(i.get("done"))})
    return out

def closing_report(meeting, items, today):
    slips = [i for i in items if i["completed_on"] > i["due"]]  # facts are computed in code, the LLM only writes prose
    facts = [{"title": i["title"], "owner": i["owner"], "due": i["due"], "completed_on": i["completed_on"],
              "slipped_days": (date.fromisoformat(i["completed_on"]) - date.fromisoformat(i["due"])).days} for i in items]
    def mock():
        lines = [f"- {i['title']} — {i['owner']}, due {i['due']}, done {i['completed_on']}" + (" (slipped)" if i in slips else "") for i in items]
        return {"subject": f"[Closed] {meeting['title']} — all {len(items)} action items done",
                "body": f"Hi all,\n\nAll action items from \"{meeting['title']}\" ({meeting['date']}) are complete as of {today}.\n\n"
                        + "\n".join(lines) + f"\n\nSlips: {len(slips)}" + (" — " + ", ".join(s['title'] for s in slips) if slips else " — none")
                        + ".\n\nThanks everyone,\nOleksii"}
    prompt = (f"Write a short closing email for the meeting '{meeting['title']}' held {meeting['date']}. All action items are done as of {today}.\n"
              f"Facts (use ONLY these, do not invent anything else): {json.dumps(facts, ensure_ascii=False)}\n"
              "Return JSON {subject, body}. subject must start with '[Closed] ' and contain the meeting title. body: greeting 'Hi all,', "
              "one-sentence outcome, a bullet list with every item as '- <title> — <owner>, due <due>, done <completed_on>' plus ' (slipped N days)' when slipped_days>0, "
              "a 'Slips:' line, and sign-off 'Thanks everyone,\\nOleksii'.")
    out = _ask("closing_report", prompt, mock, validate=lambda o: _check_report(o, meeting, items))
    return {**out, "slips": len(slips)}

def _check_report(o, meeting, items):
    problems = []
    if not str(o.get("subject", "")).startswith("[Closed]") or meeting["title"] not in o.get("subject", ""):
        problems.append("subject must start with '[Closed] ' and include the meeting title")
    missing = [i["title"] for i in items if i["title"] not in o.get("body", "")]
    if missing: problems.append(f"body is missing items: {missing}")
    return problems
