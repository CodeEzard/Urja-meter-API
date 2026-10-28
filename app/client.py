import asyncio
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings
from app.exceptions import PortalAuthError, PortalRequestError, ResourceNotFoundError


class UrjaClient:
    """HTTP client handling authentication and communication with the Urja Meter Ops portal."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.portal_url).rstrip("/")
        self.username = username or settings.username
        self.password = password or settings.password
        self.timeout = timeout or settings.request_timeout

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=False,
        )
        self._auth_lock = asyncio.Lock()
        self._authenticated_at: float = 0
        self._session_ttl: float = 3300  # Proactively refresh before the 3600s portal session expires

    async def aclose(self):
        await self._client.aclose()

    async def ensure_authenticated(self, force: bool = False):
        """Authenticate with the portal if not already authenticated or if session is expiring."""
        async with self._auth_lock:
            now = time.time()
            if not force and (now - self._authenticated_at) < self._session_ttl:
                return

            response = await self._client.post(
                "/login",
                data={"email": self.username, "password": self.password},
                headers={
                    "Origin": self.base_url,
                    "x-sveltekit-action": "true",
                },
            )

            # SvelteKit returns 200 with {"type":"redirect","status":303,"location":"/meters"}
            if response.status_code != 200 or "__Secure-better-auth.session_token" not in self._client.cookies:
                raise PortalAuthError(f"Failed to authenticate with Urja portal (HTTP {response.status_code}): {response.text}")

            self._authenticated_at = now

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Execute an authenticated request with automatic retry on session expiry."""
        await self.ensure_authenticated()

        resp = await self._client.request(method, path, **kwargs)

        # Handle expired session or unexpected unauthenticated response
        if resp.status_code in (401, 303) and "/login" in resp.headers.get("location", ""):
            await self.ensure_authenticated(force=True)
            resp = await self._client.request(method, path, **kwargs)

        if resp.status_code == 404:
            raise ResourceNotFoundError(f"Upstream resource not found: {path}")

        if not (200 <= resp.status_code < 300):
            raise PortalRequestError(
                f"Upstream request failed ({resp.status_code}) on {path}: {resp.text}",
                status_code=resp.status_code,
            )

        return resp

    async def get_signing_secret(self) -> str:
        """Fetch the HMAC signing secret required for bulk data export."""
        resp = await self._request("GET", "/portal/keys")
        body = resp.json()
        secret = body.get("data", {}).get("signingSecret")
        if not secret:
            raise PortalRequestError("Signing secret not found in /portal/keys response")
        return secret

    async def export_all_meters(self) -> List[Dict[str, Any]]:
        """Fetch all meters with hierarchy and coordinates via the signed bulk export endpoint."""
        secret = await self.get_signing_secret()
        timestamp = str(int(time.time()))

        # Canonical string expected by the portal: method \n path \n query \n timestamp
        message = f"GET\n/portal/export\npage=1\n{timestamp}"
        signature = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()

        resp = await self._request(
            "GET",
            "/portal/export?page=1",
            headers={
                "x-timestamp": timestamp,
                "x-signature": signature,
            },
        )
        data = resp.json()
        return data.get("data", [])

    async def get_transformers(self) -> List[Dict[str, Any]]:
        """Fetch distribution transformers list."""
        resp = await self._request("GET", "/portal/dts")
        data = resp.json()
        return data.get("data", []) if isinstance(data, dict) else data

    async def get_meter_energy(
        self,
        meter_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch 30-minute cumulative interval energy readings for a meter.
        Dates must be formatted as YYYY-MM-DD.
        """
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        resp = await self._request("GET", f"/portal/meters/{meter_id}/energy", params=params)
        data = resp.json()
        return data.get("data", [])

    async def get_meter_geo(self, meter_id: str) -> Dict[str, Any]:
        """Fetch geo coordinates for a single meter."""
        resp = await self._request("GET", f"/portal/meters/{meter_id}/geo")
        data = resp.json()
        return data.get("data", {})
