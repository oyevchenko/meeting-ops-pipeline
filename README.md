# meeting-ops-pipeline

Automates the PM routine that follows every meeting: **Notion AI meeting notes → LLM summary → Confluence page → action items → Jira tasks + follow-up calls + email drafts + reminders/escalations → closing report to stakeholders once everything is done.**

Dry-run by default: every external call is recorded with the real REST API shape (Confluence, Google Calendar, Gmail drafts, Jira, Slack/Telegram) and **nothing is sent**.

```mermaid
flowchart LR
  N[Notion AI export<br/>md/json] --> S[LLM: summary + decisions]
  N --> A[LLM: extract action items<br/>owner · task · due]
  S --> C[Confluence<br/>POST /wiki/rest/api/content]
  A --> J[Jira<br/>POST /rest/api/3/issue]
  A --> G[Google Calendar<br/>follow-up call on due date]
  A --> M[Gmail draft to owner]
  A --> R{Due date?}
  R -->|future| R1[Reminder T-1 + on due day<br/>Slack/Telegram/email + calendar popup]
  R -->|overdue & open| E[Escalation to Oleksii + assignee]
  J --> D{All items done?}
  D -->|yes| CR[LLM closing report<br/>done · owners · dates · slips]
  CR --> MS[Gmail draft to attendees<br/>or responsible people]
```

## Run
```bash
python -m venv .venv && . .venv/bin/activate && pip install pytest openai
python run.py            # dry-run demo, writes out/*.json
python -m pytest -q      # 10 tests
LLM_MODE=real OPENAI_API_KEY=... python run.py   # real LLM (OpenAI-compatible); mock otherwise
```
Options: `Pipeline(today, dry_run=True, stakeholders="attendees"|"responsible", channel="slack"|"telegram"|"email")`.

## Outputs
- `out/run_output.txt` – console run · `out/run_result.json` – per-item Jira key, calendar event, draft, reminders
- `out/api_calls_dry_run.json` – every request that *would* be sent · `out/closing_report.json`

## How I used this in real projects
In my delivery work I automated about 90% of the PM routine — status reports, plans, meeting summaries and follow-ups — with AI tools and by delegating to the right people. What remained for me was live communication: talking to clients and the team. The teams were set up to be autonomous, covering the basics without me hovering over them. This repo is a clean, generic reconstruction of that workflow, built on sample data.
