from pathlib import Path
from bunq.sdk.context.api_context import ApiContext
from bunq.sdk.context.api_environment_type import ApiEnvironmentType
from bunq.sdk.context.bunq_context import BunqContext

CONTEXT_FILE = Path(".bunq_context.cfg")

def ensure_context(api_key: str, environment: str, description: str = "bunq-voice") -> None:
    env = ApiEnvironmentType.SANDBOX if environment.upper() == "SANDBOX" else ApiEnvironmentType.PRODUCTION
    if CONTEXT_FILE.exists():
        ctx = ApiContext.restore(str(CONTEXT_FILE))
        try:
            ctx.ensure_session_active()
        except Exception:
            ctx = ApiContext.create(env, api_key, description)
    else:
        ctx = ApiContext.create(env, api_key, description)
    ctx.save(str(CONTEXT_FILE))
    BunqContext.load_api_context(ctx)
