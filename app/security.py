import hashlib
import hmac

from app.config import Settings


def pseudonymize_user_id(user_id: str, settings: Settings) -> str:
    key = settings.pii_hmac_key.get_secret_value().encode("utf-8")
    return hmac.new(key, user_id.encode("utf-8"), hashlib.sha256).hexdigest()
