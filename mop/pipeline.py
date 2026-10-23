"""Notion AI notes -> summary -> Confluence -> action items -> calls, emails, tasks, reminders -> closing report."""
import hashlib, html, json, pathlib, re
from datetime import date, timedelta
from . import llm
from .owners import resolve_owner
from .clients import Confluence, Calendar, Gmail, Jira, Notifier

OWNER = "oleksii.yevchenko@gmail.com"

def plan_reminders(item, email, today, channel="slack"):
    """1 day before + on due date to the assignee (cc owner); escalation to owner if overdue and not done."""
    out = []
    if item.get("done") or not item.get("due"): return out
    due = date.fromisoformat(item["due"])
    if due < today:
        out.append({"kind": "escalation", "at": today.isoformat(), "to": [OWNER, email], "channel": channel,
                    "text": f"⚠️ OVERDUE since {item['due']}: '{item['title']}' ({item['owner']}). Please give a new ETA today."})
    else:
        if due - timedelta(days=1) >= today:
            out.append({"kind": "T-1", "at": (due - timedelta(days=1)).isoformat(), "to": [email], "channel": channel,
                        "text": f"Reminder: '{item['title']}' is due tomorrow ({item['due']})."})
        out.append({"kind": "due-today", "at": item["due"], "to": list(dict.fromkeys([email, OWNER])), "channel": channel,
                    "text": f"Due today: '{item['title']}'. Reply 'done' or share blockers."})
    return out

class Pipeline:
    def __init__(self, today: date, dry_run=True, stakeholders="attendees", channel="slack", state_path=None):
        self.today, self.dry_run, self.stakeholders, self.channel = today, dry_run, stakeholders, channel
        self.state_path = pathlib.Path(state_path) if state_path else None
        self.state = json.loads(self.state_path.read_text()) if self.state_path and self.state_path.exists() else {}
        self.confluence, self.calendar, self.gmail, self.jira, self.notify = Confluence(), Calendar(), Gmail(), Jira(), Notifier()

    def _save(self):
        if self.state_path: self.state_path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))

    @staticmethod
    def meeting_key(meeting):
        return hashlib.sha256(f"{meeting['title']}|{meeting['date']}|{meeting['notes_markdown']}".encode()).hexdigest()[:16]

    def run(self, meeting):
        """Idempotent: re-ingesting the same Notion export (sync retries, manual re-run) returns the stored result
        instead of creating a second Confluence page, Jira issues, drafts and reminders."""
        key = self.meeting_key(meeting)
        if key in self.state:
            return {**self.state[key], "duplicate": True}
        res = self._run(meeting)
        self.state[key] = res; self._save()
        return res

    def _run(self, meeting):
        emails = {a["name"]: a["email"] for a in meeting["attendees"]}
        s = llm.summarize(meeting); items = llm.extract_action_items(meeting)
        sus = llm.suspicious_lines(meeting["notes_markdown"])
        allowed = {a["email"].split("@")[1] for a in meeting["attendees"]}
        for i in items:  # anything touching an outside address or living in an instruction-like line is held for a human
            ext = [d for d in re.findall(r"[\w.+-]+@([\w.-]+)", i["title"]) if d not in allowed]
            in_sus = any(i["title"][:25].lower() in l.lower() for l in sus)
            i["hold"] = (["external address: " + ", ".join(ext)] if ext else []) + (["from instruction-like text"] if in_sus else [])
        e = html.escape  # Confluence storage format is XHTML: titles/notes like '<4h', 'A & B' or '<script>' must be escaped
        body = f"<h1>{e(meeting['title'])}</h1><p>{e(s['tldr'])}</p><h2>Decisions</h2><ul>" + "".join(f"<li>{e(d)}</li>" for d in s["decisions"]) + \
               "</ul><h2>Action items</h2><ul>" + "".join(f"<li>{e(i['owner'] or 'unassigned')}: {e(i['title'])} (due {e(i['due'] or 'TBD')})</li>" for i in items) + "</ul>"
        page = self.confluence.create_page("DEL", f"{meeting['date']} {meeting['title']}", body)
        results = []
        for i in items:
            if i.get("hold"):
                self.gmail.create_draft(OWNER, f"Review held action item: {i['title']}", f"Not actioned automatically ({'; '.join(i['hold'])}). Source meeting: {meeting['title']}.")
                results.append({**i, "email": OWNER, "jira": None, "calendar_event": None, "draft": None, "reminders": [], "needs": ["human review"]})
                continue
            who, problem = resolve_owner(i.get("owner"), meeting["attendees"])
            em = who["email"] if who else OWNER  # unresolved owners go to Oleksii for triage, never silently
            if who: i = {**i, "owner": who["name"]}
            needs = [f"owner ({problem})"] if problem else []
            if not i.get("due"):  # no deadline agreed: no calendar/reminders, ask the owner of the meeting to clarify
                mail = self.gmail.create_draft(OWNER, f"Clarify deadline: {i['title']}",
                    f"Action item without a deadline from '{meeting['title']}': {i['title']} (owner: {i['owner'] or 'unassigned'}). Please agree a due date.")
                results.append({**i, "email": em, "jira": None, "calendar_event": None, "draft": mail["id"], "reminders": [], "needs": needs + ["due_date"]})
                continue
            issue = self.jira.create_issue(i["title"], em, i["due"])
            call = self.calendar.create_event(f"Follow-up: {i['title']}", i["due"], [em, OWNER],
                                              reminders=[{"method": "popup", "minutes": 1440}, {"method": "email", "minutes": 60}])
            mail = self.gmail.create_draft(em, f"Action item: {i['title']} (due {i['due']})",
                f"Hi {i['owner'].split()[0]},\n\nFrom today's '{meeting['title']}': {i['title']}.\nDue: {i['due']}. Jira: {issue['key']}.\n"
                f"I booked a short follow-up on the due date.\n\nThanks,\nOleksii")
            rems = [dict(r, scheduled=self.notify.schedule(r["channel"], ",".join(r["to"]), r["at"], r["text"])["id"])
                    for r in plan_reminders(i, em, self.today, self.channel)]
            if problem:
                self.gmail.create_draft(OWNER, f"Clarify owner: {i['title']}", f"From '{meeting['title']}': '{i['title']}' — {problem}. Please assign an owner.")
            results.append({**i, "email": em, "jira": issue["key"], "calendar_event": call["id"], "draft": mail["id"], "reminders": rems, "needs": needs})
        return {"dry_run": self.dry_run, "summary": s, "suspicious_lines": sus, "confluence_page": page["id"], "items": results}

    def close_if_done(self, meeting, items):
        """items need 'completed_on'. Returns None until every item is done."""
        if not items or not all(i.get("completed_on") for i in items): return None
        rep = llm.closing_report(meeting, items, max(i["completed_on"] for i in items))
        to = [a["email"] for a in meeting["attendees"]] if self.stakeholders == "attendees" else sorted({i["email"] for i in items} | {OWNER})
        draft = self.gmail.create_draft(", ".join(to), rep["subject"], rep["body"])
        return {**rep, "to": to, "gmail_draft": draft["id"], "sent": False if self.dry_run else "would send (not implemented in demo)"}
