"""Notion AI notes -> summary -> Confluence -> action items -> calls, emails, tasks, reminders -> closing report."""
from datetime import date, timedelta
from . import llm
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
    def __init__(self, today: date, dry_run=True, stakeholders="attendees", channel="slack"):
        self.today, self.dry_run, self.stakeholders, self.channel = today, dry_run, stakeholders, channel
        self.confluence, self.calendar, self.gmail, self.jira, self.notify = Confluence(), Calendar(), Gmail(), Jira(), Notifier()

    def run(self, meeting):
        emails = {a["name"]: a["email"] for a in meeting["attendees"]}
        s = llm.summarize(meeting); items = llm.extract_action_items(meeting)
        html = f"<h1>{meeting['title']}</h1><p>{s['tldr']}</p><h2>Decisions</h2><ul>" + "".join(f"<li>{d}</li>" for d in s["decisions"]) + \
               "</ul><h2>Action items</h2><ul>" + "".join(f"<li>{i['owner']}: {i['title']} (due {i['due']})</li>" for i in items) + "</ul>"
        page = self.confluence.create_page("DEL", f"{meeting['date']} {meeting['title']}", html)
        results = []
        for i in items:
            em = emails.get(i["owner"], OWNER)
            if not i.get("due"):  # no deadline agreed: no calendar/reminders, ask the owner of the meeting to clarify
                mail = self.gmail.create_draft(OWNER, f"Clarify deadline: {i['title']}",
                    f"Action item without a deadline from '{meeting['title']}': {i['title']} (owner: {i['owner'] or 'unassigned'}). Please agree a due date.")
                results.append({**i, "email": em, "jira": None, "calendar_event": None, "draft": mail["id"], "reminders": [], "needs": ["due_date"]})
                continue
            issue = self.jira.create_issue(i["title"], em, i["due"])
            call = self.calendar.create_event(f"Follow-up: {i['title']}", i["due"], [em, OWNER],
                                              reminders=[{"method": "popup", "minutes": 1440}, {"method": "email", "minutes": 60}])
            mail = self.gmail.create_draft(em, f"Action item: {i['title']} (due {i['due']})",
                f"Hi {i['owner'].split()[0]},\n\nFrom today's '{meeting['title']}': {i['title']}.\nDue: {i['due']}. Jira: {issue['key']}.\n"
                f"I booked a short follow-up on the due date.\n\nThanks,\nOleksii")
            rems = [dict(r, scheduled=self.notify.schedule(r["channel"], ",".join(r["to"]), r["at"], r["text"])["id"])
                    for r in plan_reminders(i, em, self.today, self.channel)]
            results.append({**i, "email": em, "jira": issue["key"], "calendar_event": call["id"], "draft": mail["id"], "reminders": rems})
        return {"dry_run": self.dry_run, "summary": s, "confluence_page": page["id"], "items": results}

    def close_if_done(self, meeting, items):
        """items need 'completed_on'. Returns None until every item is done."""
        if not items or not all(i.get("completed_on") for i in items): return None
        rep = llm.closing_report(meeting, items, max(i["completed_on"] for i in items))
        to = [a["email"] for a in meeting["attendees"]] if self.stakeholders == "attendees" else sorted({i["email"] for i in items} | {OWNER})
        draft = self.gmail.create_draft(", ".join(to), rep["subject"], rep["body"])
        return {**rep, "to": to, "gmail_draft": draft["id"], "sent": False if self.dry_run else "would send (not implemented in demo)"}
