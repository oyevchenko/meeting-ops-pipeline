"""Live LLM evals — hit the real model. Run: RUN_LIVE=1 pytest tests/test_live_evals.py"""
import json, os, pathlib, pytest
from datetime import date
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="live evals need RUN_LIVE=1 and an API key")
S = pathlib.Path(__file__).parent.parent / "samples"

@pytest.fixture(autouse=True)
def real(monkeypatch): monkeypatch.delenv("LLM_MODE", raising=False)

def test_live_closing_report_lists_every_item_and_slip():
    from mop.pipeline import Pipeline
    from mop import llm
    m = json.loads((S / "notion_ai_export.json").read_text())
    p = Pipeline(date(2026, 10, 23)); items = p.run(m)["items"]
    for i, d in zip(items, ["2026-10-24", "2026-10-23", "2026-10-25", "2026-10-27"]): i["completed_on"] = d
    c = p.close_if_done(m, items)
    assert llm.TRACE[-1]["backend"] != "mock (fallback)", llm.TRACE[-1]
    assert c["subject"].startswith("[Closed]") and m["title"] in c["subject"]
    assert all(i["title"] in c["body"] for i in items) and "3 days" in c["body"]
