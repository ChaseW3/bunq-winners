import sys
sys.path.insert(0, ".")

from backend.config import load
from backend.bunq_client.bootstrap import ensure_context
from backend.bunq_client.client import RealBunqClient

cfg = load()
ensure_context(cfg.bunq_api_key, cfg.bunq_environment)
c = RealBunqClient()
print("primary:", c.primary_account_id())
print("balance:", c.balance())
print("payments:", c.recent_payments(limit=3))
