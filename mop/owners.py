"""Map the owner name as written in notes ('Діма', 'Olena', 'Mark') to an attendee. Ambiguous/unknown -> None + reason."""
ALIASES = {"діма": "dmytro", "дмитро": "dmytro", "dima": "dmytro", "олена": "olena", "лена": "olena", "олексій": "oleksii",
           "льоша": "oleksii", "alex": "oleksii", "марк": "mark", "анна": "anna", "аня": "anna"}

def resolve_owner(raw, attendees):
    if not raw:
        return None, "unassigned"
    key = raw.strip().lower()
    exact = [a for a in attendees if a["name"].lower() == key]
    if exact: return exact[0], None
    first = ALIASES.get(key, key).split()[0]
    hits = [a for a in attendees if a["name"].lower().split()[0] == first]
    if len(hits) == 1: return hits[0], None
    if len(hits) > 1: return None, "ambiguous: " + " / ".join(a["name"] for a in hits)
    return None, f"unknown owner '{raw}'"
