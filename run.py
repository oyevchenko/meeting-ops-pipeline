"""Demo: run pipeline on sample Notion AI export (dry-run), then simulate completion -> closing report."""
import json, pathlib, sys
from datetime import date
from mop.pipeline import Pipeline
SRC = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "samples/notion_ai_export.json"
m = json.loads(pathlib.Path(SRC).read_text())
p = Pipeline(today=date(2026, 10, 23))  # pass state_path="out/state.json" for idempotent re-runs
r = p.run(m)
from mop.llm import backends, TRACE
print(f"🧾 {m['title']}  (dry-run={r['dry_run']}, LLM={backends()})\n   TL;DR: {r['summary']['tldr']}\n   Confluence page id={r['confluence_page']} → POST /wiki/rest/api/content")
for i in r["items"]:
    print(f"\n • {i['title']}\n   owner={i['owner']} due={i['due']} (raw: {i.get('due_raw')}) jira={i['jira']} cal_event={i['calendar_event']} gmail_draft={i['draft']}")
    if i.get("needs"): print(f"   ⚠️  needs: {', '.join(i['needs'])}")
    for x in i["reminders"]: print(f"   ⏰ {x['kind']:<10} {x['at']} via {x['channel']} → {', '.join(x['to'])}")
if SRC != "samples/notion_ai_export.json":
    out = pathlib.Path("out/edge"); out.mkdir(parents=True, exist_ok=True)
    (out / (pathlib.Path(SRC).stem + ".json")).write_text(json.dumps(r, indent=2, ensure_ascii=False))
    from mop.llm import totals; print("\n💰", totals()); sys.exit()
done = ["2026-10-24", "2026-10-23", "2026-10-25", "2026-10-27"]
items = [{**i, "completed_on": d} for i, d in zip(r["items"], done)]
c = p.close_if_done(m, items)
print(f"\n📬 Closing report (Gmail DRAFT, not sent) → {', '.join(c['to'])}\n   Subject: {c['subject']}\n" + "\n".join("   " + l for l in c["body"].splitlines()))
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
(out / "run_result.json").write_text(json.dumps(r, indent=2, ensure_ascii=False))
(out / "closing_report.json").write_text(json.dumps(c, indent=2, ensure_ascii=False))
(out / "api_calls_dry_run.json").write_text(json.dumps({k: getattr(p, k).calls for k in ["confluence", "jira", "calendar", "gmail", "notify"]}, indent=2, ensure_ascii=False))
(out / "llm_trace.json").write_text(json.dumps(TRACE, indent=2))
print("\n🔎 LLM trace: " + "; ".join(f"{t['step']}→{t['backend']}" + (f" (skipped {t['errors']})" if t['errors'] else "") for t in TRACE))
from mop.llm import totals
t = totals(); print(f"💰 {t['llm_calls']} LLM calls · {t['prompt_tokens']}+{t['completion_tokens']} tokens · ${t['cost_usd']} · {t['latency_ms']} ms")
