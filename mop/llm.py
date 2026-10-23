"""Pluggable LLM: OpenAI-compatible API when LLM_MODE=real and a key exists; deterministic mock otherwise."""
import json, os, re

def _client():
    if os.getenv("LLM_MODE") != "real": return None
    key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key: return None
    from openai import OpenAI
    base = os.getenv("OPENAI_BASE_URL") or (None if os.getenv("OPENAI_API_KEY") else "https://generativelanguage.googleapis.com/v1beta/openai/")
    return OpenAI(api_key=key, base_url=base), os.getenv("LLM_MODEL", "gpt-4o-mini")

def _ask(prompt, fallback):
    c = _client()
    if c:
        try:
            r = c[0].chat.completions.create(model=c[1], temperature=0, response_format={"type": "json_object"},
                                             messages=[{"role": "user", "content": prompt}])
            return json.loads(r.choices[0].message.content), "llm"
        except Exception: pass
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
