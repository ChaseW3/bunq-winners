import sys, os
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from backend.bunq_client.bootstrap import ensure_context
from backend.bunq_client.client import RealBunqClient

api_key = os.environ["BUNQ_API_KEY"]
environment = os.environ.get("BUNQ_ENVIRONMENT", "SANDBOX")

ensure_context(api_key, environment)
c = RealBunqClient()
print("primary account id:", c.primary_account_id())
print("balance:", c.balance())
print("recent payments:", c.recent_payments(limit=3))
