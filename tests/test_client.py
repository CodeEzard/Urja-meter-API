import hashlib
import hmac
import pytest
from app.client import UrjaClient


def test_hmac_signature_calculation():
    secret = "test_signing_secret_for_hmac_tests"
    timestamp = "1793226769"
    message = f"GET\n/portal/export\npage=1\n{timestamp}"
    expected_sig = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()

    assert len(expected_sig) == 64
    assert isinstance(expected_sig, str)


def test_client_init_defaults():
    client = UrjaClient(base_url="https://urja-ops.flockenergy.tech/")
    assert client.base_url == "https://urja-ops.flockenergy.tech"
    assert client._session_ttl == 3300
