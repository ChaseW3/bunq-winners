from backend.bunq_client import BunqClient

def find_contact(client: BunqClient, query: str) -> list[dict]:
    q = query.strip().lower()
    if not q:
        return []
    matches = [c for c in client.list_contacts() if q in c.name.lower()]
    return [{"id": c.id, "name": c.name, "iban": c.iban} for c in matches]
