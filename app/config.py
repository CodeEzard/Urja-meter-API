import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    portal_url: str = os.getenv("URJA_PORTAL_URL", "https://urja-ops.flockenergy.tech").rstrip("/")
    username: str = os.getenv("URJA_USERNAME", "")
    password: str = os.getenv("URJA_PASSWORD", "")
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "900"))
    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "15.0"))
    app_host: str = os.getenv("HOST", "0.0.0.0")
    app_port: int = int(os.getenv("PORT", "8000"))


settings = Settings()
