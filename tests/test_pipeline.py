import json, pathlib
from datetime import date
from mop.pipeline import Pipeline, plan_reminders
from mop import llm
M = json.loads((pathlib.Path(__file__).parent.parent / "samples/notion_ai_export.json").read_text())
T = date(2026, 10, 23)

def test_extracts_four_action_items_with_owners_and_dates():
    items = llm.extract_action_items(M)
    assert [i["owner"] for i in items] == ["Dmytro Shevchuk", "Olena Bondar", "Anna Koval", "Oleksii Yevchenko"]
    assert items[0]["due"] == "2026-10-24"

def test_summary_has_decisions():
    s = llm.summarize(M); assert "voice-agent" in s["tldr"] and len(s["decisions"]) == 2

def test_end_to_end_dry_run_creates_artifacts_and_sends_nothing():
    p = Pipeline(T); r = p.run(M)
    assert len(p.confluence.calls) == 1 and p.confluence.calls[0]["url"] == "/wiki/rest/api/content"
    assert len(p.jira.calls) == len(p.calendar.calls) == len(p.gmail.calls) == 4
    assert all(c["body"]["status"] == "DRAFT" for c in p.gmail.calls)
    assert r["dry_run"] is True

def test_reminders_t_minus_1_and_due_day():
    rem = plan_reminders({"title": "x", "owner": "D", "due": "2026-10-28"}, "d@x", T)
    assert [r["kind"] for r in rem] == ["T-1", "due-today"] and rem[0]["at"] == "2026-10-27"

def test_reminder_due_tomorrow_skips_nothing_and_today_only_due_day():
    assert [r["kind"] for r in plan_reminders({"title": "x", "owner": "D", "due": "2026-10-23"}, "d@x", T)] == ["due-today"]

def test_overdue_escalates_to_owner():
    rem = plan_reminders({"title": "x", "owner": "Anna", "due": "2026-10-22"}, "a@x", T)
    assert rem[0]["kind"] == "escalation" and "oleksii.yevchenko@gmail.com" in rem[0]["to"]

def test_done_items_get_no_reminders():
    assert plan_reminders({"title": "x", "owner": "D", "due": "2026-10-28", "done": True}, "d@x", T) == []

def test_no_closing_report_until_all_done():
    p = Pipeline(T); items = p.run(M)["items"]
    items[0]["completed_on"] = "2026-10-24"
    assert p.close_if_done(M, items) is None

def test_closing_report_lists_slips_and_goes_to_attendees_as_draft():
    p = Pipeline(T); items = p.run(M)["items"]
    for i, d in zip(items, ["2026-10-24", "2026-10-23", "2026-10-25", "2026-10-27"]): i["completed_on"] = d
    c = p.close_if_done(M, items)
    assert c["slips"] == 1 and "Telegram bot naming" in c["body"] and c["sent"] is False
    assert len(c["to"]) == 4 and p.gmail.calls[-1]["body"]["status"] == "DRAFT"

def test_closing_report_responsible_only_mode():
    p = Pipeline(T, stakeholders="responsible"); items = p.run(M)["items"]
    for i in items: i["completed_on"] = i["due"]
    c = p.close_if_done(M, items); assert c["slips"] == 0 and "oleksii.yevchenko@gmail.com" in c["to"]

def test_trace_records_backend_per_step_and_falls_through_models(monkeypatch):
    import httpx, openai
    from types import SimpleNamespace as N
    calls = []
    class Cli:
        chat = property(lambda s: s); completions = property(lambda s: s)
        def create(self, model, **kw):
            calls.append(model)
            if model == "m1":
                raise openai.RateLimitError("You exceeded your current quota", response=httpx.Response(429, request=httpx.Request("POST", "http://x")), body=None)
            return N(choices=[N(message=N(content='{"tldr": "t", "decisions": []}'))], usage=N(prompt_tokens=5, completion_tokens=3))
    monkeypatch.setattr(llm, "_client", lambda: (Cli(), ["m1", "m2"]))
    llm.TRACE.clear()
    assert llm.summarize(M)["tldr"] == "t"
    assert calls == ["m1", "m2"]  # quota error: no retries on m1, straight to m2
    assert llm.TRACE[-1]["backend"] == "m2" and "m1: RateLimitError" in llm.TRACE[-1]["errors"]

def _items_done():
    p = Pipeline(T); items = p.run(M)["items"]
    for i, d in zip(items, ["2026-10-24", "2026-10-23", "2026-10-25", "2026-10-27"]): i["completed_on"] = d
    return items

def test_closing_report_validator_flags_generic_subject_and_missing_items():
    items = _items_done()
    probs = llm._check_report({"subject": "Project Closing Report: Task Completion Summary", "body": "All tasks done."}, M, items)
    assert len(probs) == 2 and "missing items" in probs[1]

def test_closing_report_slip_count_is_computed_not_llm(monkeypatch):
    items = _items_done()
    monkeypatch.setattr(llm, "_ask", lambda *a, **k: {"subject": "[Closed] x", "body": "b", "slips": 0})
    assert llm.closing_report(M, items, "2026-10-27")["slips"] == 1
