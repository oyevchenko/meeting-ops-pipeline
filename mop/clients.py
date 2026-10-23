"""Mock clients shaped like the real REST APIs. Dry-run: requests are recorded, never sent."""
import itertools
class _Mock:
    def __init__(self): self.calls, self._id = [], itertools.count(1)
    def _rec(self, method, url, body):
        self.calls.append({"method": method, "url": url, "body": body}); return {"id": str(next(self._id)), **body}

class Confluence(_Mock):  # POST /wiki/rest/api/content
    def create_page(self, space, title, html):
        return self._rec("POST", "/wiki/rest/api/content", {"type": "page", "title": title, "space": {"key": space},
                         "body": {"storage": {"value": html, "representation": "storage"}}})
class Calendar(_Mock):  # POST /calendar/v3/calendars/primary/events
    def create_event(self, summary, start, attendees, reminders=None):
        return self._rec("POST", "/calendar/v3/calendars/primary/events", {"summary": summary,
                         "start": {"date": start}, "end": {"date": start}, "attendees": [{"email": a} for a in attendees],
                         "reminders": {"useDefault": False, "overrides": reminders or []}})
class Gmail(_Mock):  # POST /gmail/v1/users/me/drafts  (drafts only, never send)
    def create_draft(self, to, subject, body):
        return self._rec("POST", "/gmail/v1/users/me/drafts", {"message": {"to": to, "subject": subject, "body": body}, "status": "DRAFT"})
class Jira(_Mock):  # POST /rest/api/3/issue
    def create_issue(self, summary, assignee, due):
        r = self._rec("POST", "/rest/api/3/issue", {"fields": {"project": {"key": "OPS"}, "issuetype": {"name": "Task"},
                      "summary": summary, "assignee": {"emailAddress": assignee}, "duedate": due}})
        r["key"] = f"OPS-{200 + int(r['id'])}"; return r
class Notifier(_Mock):  # Slack chat.scheduleMessage / Telegram sendMessage / email — scheduled, dry-run
    def schedule(self, channel, to, at, text):
        return self._rec("POST", {"slack": "/api/chat.scheduleMessage", "telegram": "/bot<token>/sendMessage",
                                  "email": "/gmail/v1/users/me/drafts"}[channel], {"channel": channel, "to": to, "post_at": at, "text": text})
