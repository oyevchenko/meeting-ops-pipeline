"""Demo: run pipeline on sample Notion AI export (dry-run), then simulate completion -> closing report."""
import json, pathlib, sys
from datetime import date
from mop.pipeline import Pipeline
m = json.loads(pathlib.Path("samples/notion_ai_export.json").read_text())
p = Pipeline(today=date(2026, 10, 23))
r = p.run(m)
from mop.llm import LAST_BACKEND
print(f"🧾 {m['title']}  (dry-run={r['dry_run']}, LLM={LAST_BACKEND['value']})\n   TL;DR: {r['summary']['tldr']}\n   Confluence page id={r['confluence_page']} → POST /wiki/rest/api/content")
for i in r["items"]:
    print(f"\n • {i['title']}\n   owner={i['owner']} due={i['due']} jira={i['jira']} cal_event={i['calendar_event']} gmail_draft={i['draft']}")
    for x in i["reminders"]: print(f"   ⏰ {x['kind']:<10} {x['at']} via {x['channel']} → {', '.join(x['to'])}")
done = ["2026-10-24", "2026-10-23", "2026-10-25", "2026-10-27"]
items = [{**i, "completed_on": d} for i, d in zip(r["items"], done)]
c = p.close_if_done(m, items)
print(f"\n📬 Closing report (Gmail DRAFT, not sent) → {', '.join(c['to'])}\n   Subject: {c['subject']}\n" + "\n".join("   " + l for l in c["body"].splitlines()))
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
(out / "run_result.json").write_text(json.dumps(r, indent=2, ensure_ascii=False))
(out / "closing_report.json").write_text(json.dumps(c, indent=2, ensure_ascii=False))
(out / "api_calls_dry_run.json").write_text(json.dumps({k: getattr(p, k).calls for k in ["confluence", "jira", "calendar", "gmail", "notify"]}, indent=2, ensure_ascii=False))
