"""Validate and normalise a Notion AI export before any LLM call or API side effect."""
import json, re
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, ValidationError, field_validator

class Attendee(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Optional[str] = None

class Meeting(BaseModel):
    title: str = Field(min_length=1)
    date: str
    attendees: list[Attendee] = []
    notes_markdown: str = Field(min_length=1)
    source: Optional[str] = None

    @field_validator("date", mode="before")
    @classmethod
    def iso_date(cls, v):  # Notion exports seen as '2026-10-23', '23.10.2026', '2026-10-23T10:00:00Z'
        v = str(v).strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
            try: return datetime.strptime(v[:10], fmt).date().isoformat()
            except ValueError: pass
        raise ValueError(f"unrecognised date '{v}'")

class InputError(ValueError):
    pass

def load_meeting(raw) -> dict:
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        return Meeting.model_validate(data).model_dump()
    except json.JSONDecodeError as e:
        raise InputError(f"export is not valid JSON: {e.msg} at line {e.lineno}") from None
    except ValidationError as e:
        raise InputError("; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from None
