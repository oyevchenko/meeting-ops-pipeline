# Iterations log

Debug/adjust iterations against the real LLM (Gemini via its OpenAI-compatible endpoint). One commit per entry: what I saw in a real run, the fix, and the regression test.

## 1. Model fallback chain, quota-aware retries, per-step LLM trace
- **Observed:** First real run: the console said 'LLM=mock (fallback: RateLimitError)' yet the summary text was clearly model-written — steps were silently mixing real and mock output, and the label only reflected the last call. gemini-3-flash-preview was returning 429 quota errors.
- **Fix:** Each step goes through _ask(step, ...): models tried in order (LLM_MODEL then LLM_FALLBACK_MODELS), transient errors retried with backoff, quota 429 not retried; TRACE records per step which model answered, skipped models, tokens and latency; written to out/llm_trace.json and printed by run.py. Rerun: all 3 steps served by gemini-flash-lite-latest, with the skip visible.
- **Test:** test_trace_records_backend_per_step_and_falls_through_models

## 2. Closing report: grounded facts, required structure, validation with re-ask
- **Observed:** Real closing email had a generic subject ('Project Closing Report: Task Completion Summary') with no meeting title, no greeting or item list, and invented a claim ('All reminders and escalations for this period have been processed'). The prompt only passed raw items, not the meeting.
- **Fix:** Prompt now gets the meeting title/date and computed facts (slipped_days) and is told to use only them; subject/body format is specified; _check_report() validates subject + every item present and triggers one re-ask; slip count is computed in code, not taken from the model. Live rerun: '[Closed] Weekly Delivery Sync — Voice Agent Rollout', all 4 items listed, '(slipped 3 days)'.
- **Test:** test_closing_report_validator_flags_generic_subject_and_missing_items, test_closing_report_slip_count_is_computed_not_llm, live: test_live_closing_report_lists_every_item_and_slip

## 3. Resolve relative deadlines to ISO dates; handle items without a deadline
- **Observed:** Real extraction on samples/edge/messy_ua_mixed.json (UA/EN mixed notes) returned due as free text: "наступна п'ятниця", 'end of next week', 'ASAP', '3 листопада', null. Pipeline.run() then crashed: TypeError in date.fromisoformat.
- **Fix:** Prompt now includes the meeting date + weekday, rules for relative dates, keeps due_raw; _check_items() rejects non-ISO dues and triggers a re-ask; items with due=null skip calendar/reminders and produce a 'Clarify deadline' draft to Oleksii. Live rerun: all dues ISO, null for the unassigned Confluence item.
- **Test:** test_free_text_due_dates_fail_validation, test_item_without_due_date_gets_clarification_not_reminders, live: test_live_relative_dates_resolved_from_meeting_date

## 4. Deterministic resolver for deadline phrases; LLM date only as fallback
- **Observed:** Two live runs of the same notes gave different dates for "до наступної п'ятниці" from a Friday meeting: 2026-11-06 in one run, 2026-10-30 in the next (the live eval failed once, then passed). LLM date arithmetic isn't reliable enough for reminders and escalations.
- **Fix:** mop/dates.py resolve(): EN/UA rules for next <weekday>, end of (next) week, by Monday/до понеділка, ASAP/терміново (next business day), tomorrow, '3 листопада'/'Nov 3' (rolls to next year if passed), ISO. The rule result wins over the LLM; due_source = rule|llm|None is kept per item.
- **Test:** tests/test_dates.py: 15 parametrized cases + test_rule_overrides_inconsistent_llm_date

## 5. Resolve owners to attendees (aliases, first names); flag ambiguous/unassigned
- **Observed:** On the messy UA/EN notes the model returned owners as written ('Діма', 'Olena', 'Олена', 'Mark', 'Oleksii', null). The exact-name lookup failed for all of them, so every task, email draft and reminder silently went to Oleksii, including the client CTO's. 'Діма' could be either of two Dmytros. A test on these notes also showed the offline mock summarizer crashing (AttributeError) when a '## Decisions' section is missing.
- **Fix:** mop/owners.py resolve_owner(): exact name, then first name with UA/EN aliases (Діма→Dmytro, Олена→Olena...). Ambiguous or unknown owners are routed to Oleksii with needs=['owner (...)'] and a 'Clarify owner' draft. The mock summarizer now tolerates missing sections. Rerun: Olena/Mark/Oleksii resolved, Діма flagged ambiguous, unassigned item flagged.
- **Test:** test_owner_aliases_and_first_names_resolve_to_attendees, test_ambiguous_and_missing_owner_are_flagged, test_pipeline_routes_ambiguous_owner_to_oleksii_with_clarification

