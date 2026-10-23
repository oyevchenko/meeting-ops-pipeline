"""Pluggable LLM: real OpenAI-compatible API by default when OPENAI_API_KEY or GEMINI_API_KEY is set
(Gemini via its OpenAI-compatible endpoint); deterministic mock when LLM_MODE=mock or no key."""
import json, os, re

def _client():
    if os.getenv("LLM_MODE") == "mock": return None
    key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key: return None
    from openai import OpenAI
    base = os.getenv("OPENAI_BASE_URL") or (None if os.getenv("OPENAI_API_KEY") else "https://generativelanguage.googleapis.com/v1beta/openai/")
    default = "gpt-4o-mini" if os.getenv("OPENAI_API_KEY") else "gemini-3-flash-preview"
    return OpenAI(api_key=key, base_url=base, timeout=60), os.getenv("LLM_MODEL", default)

LAST_BACKEND = {"value": "mock"}

def _ask(prompt, fallback):
    c = _client()
    if c:
        try:
            r = c[0].chat.completions.create(model=c[1], temperature=0, response_format={"type": "json_object"},
                                             messages=[{"role": "user", "content": prompt}])
            LAST_BACKEND["value"] = c[1]
            return json.loads(r.choices[0].message.content), "llm"
        except Exception as e:
            LAST_BACKEND["value"] = f"mock (fallback: {type(e).__name__})"
            return fallback(), "mock"
    LAST_BACKEND["value"] = "mock"
    return fallback(), "mock"

AI_RE = re.compile(r"- \[( |x)\] @([^:]+):\s*(.+?)\s+—\s+due\s+(\d{4}-\d{2}-\d{2})")

def summarize(meeting):
    md = meeting["notes_markdown"]
    def mock():
        sec = lambda h: re.search(rf"## {h}\n(.+?)(\n## |\Z)", md, re.S).group(1).strip()
        return {"tldr": sec("Summary").split("\n")[0], "decisions": [l[2:] for l in sec("Decisions").splitlines()]}
    return _ask(f"Summarize as JSON {{tldr, decisions[]}}:\n{md}", mock)[0]

def extract_action_items(meeting):
    def mock():
        return {"items": [{"owner": o.strip(), "title": t, "due": d, "done": x == "x"} for x, o, t, d in AI_RE.findall(meeting["notes_markdown"])]}
    return _ask(f"Extract action items as JSON {{items:[{{owner,title,due,done}}]}}:\n{meeting['notes_markdown']}", mock)[0]["items"]

def closing_report(meeting, items, today):
    def mock():
        slips = [i for i in items if i["completed_on"] > i["due"]]
        lines = [f"- {i['title']} — {i['owner']}, due {i['due']}, done {i['completed_on']}" + (" (slipped)" if i in slips else "") for i in items]
        return {"subject": f"[Closed] {meeting['title']} — all {len(items)} action items done",
                "body": f"Hi all,\n\nAll action items from \"{meeting['title']}\" ({meeting['date']}) are complete as of {today}.\n\n"
                        + "\n".join(lines) + f"\n\nSlips: {len(slips)}" + (" — " + ", ".join(s['title'] for s in slips) if slips else " — none")
                        + ".\n\nThanks everyone,\nOleksii", "slips": len(slips)}
    return _ask(f"Write a closing report JSON {{subject, body, slips}} for: {json.dumps(items)}", mock)[0]
