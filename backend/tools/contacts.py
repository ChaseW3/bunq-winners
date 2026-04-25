from difflib import SequenceMatcher
from backend.bunq_client import BunqClient

# Similarity threshold for fuzzy matches (0.0 = anything matches, 1.0 = identical only).
# 0.7 catches typical STT mistakes like "Wayne" vs "Wang" without matching unrelated names.
FUZZY_THRESHOLD = 0.7


def find_contact(client: BunqClient, query: str) -> dict:
    q = query.strip().lower()
    if not q:
        return {"match": "none", "contacts": []}

    contacts = list(client.list_contacts())

    # 1) Exact substring match — "Sophie" matches both "Sophie van Dijk" and "Sophie Wang".
    substring_matches = [c for c in contacts if q in c.name.lower()]
    if len(substring_matches) == 1:
        c = substring_matches[0]
        return {"match": "exact", "name": c.name, "iban": c.iban}
    if len(substring_matches) > 1:
        return {
            "match": "multiple",
            "contacts": [{"name": c.name, "iban": c.iban} for c in substring_matches],
        }

    # 2) Fuzzy fallback — catches STT errors. Score every contact, keep those above threshold.
    scored = sorted(
        ((SequenceMatcher(None, q, c.name.lower()).ratio(), c) for c in contacts),
        key=lambda x: x[0],
        reverse=True,
    )
    fuzzy_matches = [(score, c) for score, c in scored if score >= FUZZY_THRESHOLD]

    if len(fuzzy_matches) == 1:
        c = fuzzy_matches[0][1]
        return {"match": "fuzzy", "name": c.name, "iban": c.iban}
    if len(fuzzy_matches) > 1:
        return {
            "match": "multiple",
            "contacts": [{"name": c.name, "iban": c.iban} for _, c in fuzzy_matches],
        }

    return {"match": "none", "contacts": []}
