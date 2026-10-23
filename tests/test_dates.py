from datetime import date
import pytest
from mop.dates import resolve
FRI = date(2026, 10, 23)  # Friday
@pytest.mark.parametrize("raw,exp", [
    ("до наступної п'ятниці", "2026-10-30"), ("next Friday", "2026-10-30"), ("by end of next week", "2026-10-30"),
    ("end of week", "2026-10-23"), ("до понеділка", "2026-10-26"), ("by Monday", "2026-10-26"), ("ASAP", "2026-10-26"),
    ("терміново", "2026-10-26"), ("3 листопада", "2026-11-03"), ("Nov 3", "2026-11-03"), ("5 жовтня", "2027-10-05"),
    ("2026-12-01", "2026-12-01"), ("tomorrow", "2026-10-24"), (None, None), ("коли буде час", None)])
def test_resolve(raw, exp):
    r = resolve(raw, FRI); assert (r.isoformat() if r else None) == exp

def test_rule_overrides_inconsistent_llm_date(monkeypatch):
    from mop import llm
    monkeypatch.setattr(llm, "_ask", lambda *a, **k: {"items": [{"owner": "Діма", "title": "мапінг", "due": "2026-11-06", "due_raw": "до наступної п'ятниці"}]})
    it = llm.extract_action_items({"date": "2026-10-23", "notes_markdown": ""})[0]
    assert it["due"] == "2026-10-30" and it["due_source"] == "rule"
