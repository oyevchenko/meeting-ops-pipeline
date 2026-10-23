"""Deterministic resolver for common deadline phrases (EN/UA). The LLM's ISO date is only used when this returns None:
models were inconsistent on 'next Friday' from a Friday meeting (2026-10-30 in one run, 2026-11-06 in another)."""
import re
from datetime import date, timedelta

WD = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
      "понеділ": 0, "вівтор": 1, "серед": 2, "четвер": 3, "п'ятниц": 4, "пятниц": 4, "субот": 5, "неділ": 6}
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
          "січ": 1, "лют": 2, "берез": 3, "квіт": 4, "трав": 5, "черв": 6, "лип": 7, "серп": 8, "верес": 9, "жовт": 10, "листопад": 11, "груд": 12}

def _wd(t):
    return next((v for k, v in WD.items() if k in t), None)

def _next_business_day(d):
    d += timedelta(days=1)
    while d.weekday() >= 5: d += timedelta(days=1)
    return d

def resolve(raw: str | None, meeting: date) -> date | None:
    if not raw: return None
    t = raw.lower().replace("’", "'").strip()
    if m := re.search(r"\d{4}-\d{2}-\d{2}", t): return date.fromisoformat(m.group())
    if re.search(r"asap|терміново|якнайшвидше|as soon as", t): return _next_business_day(meeting)
    if re.search(r"tomorrow|завтра", t): return meeting + timedelta(days=1)
    next_week = re.search(r"next|наступн", t)
    monday = meeting - timedelta(days=meeting.weekday())
    if re.search(r"end of (the |next )?week|кін(ця|ець) (наступного )?тижня", t):
        return monday + timedelta(days=4 + (7 if next_week else 0))
    if (w := _wd(t)) is not None:
        if next_week:  # 'next Friday' = that weekday in the following calendar week
            return monday + timedelta(days=7 + w)
        days = (w - meeting.weekday()) % 7 or 7  # 'by Monday' / 'до понеділка' = the next such day
        return meeting + timedelta(days=days)
    if m := re.search(r"(\d{1,2})\s+([a-zа-яії]+)|([a-z]+)\s+(\d{1,2})", t):
        day, mon = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        month = next((v for k, v in MONTHS.items() if mon.startswith(k)), None)
        if month:
            d = date(meeting.year, month, int(day))
            return d if d >= meeting else date(meeting.year + 1, month, int(day))
    return None
