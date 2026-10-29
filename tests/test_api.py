import json
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient

from app.client import UrjaClient
from app.dependencies import get_client, get_service
from app.main import app
from app.service import MeterService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_client():
    client = AsyncMock(spec=UrjaClient)

    with open(FIXTURES_DIR / "export_sample.json", "r") as f:
        export_data = json.load(f)
    with open(FIXTURES_DIR / "dts_sample.json", "r") as f:
        dts_data = json.load(f)
    with open(FIXTURES_DIR / "energy_sample.json", "r") as f:
        energy_data = json.load(f)

    client.export_all_meters.return_value = export_data["data"]
    client.get_transformers.return_value = dts_data["data"]
    client.get_meter_energy.return_value = energy_data["data"]
    client._client = AsyncMock()
    client._client.cookies = {"__Secure-better-auth.session_token": "mock_token"}

    return client


@pytest.fixture
def test_app(mock_client):
    service = MeterService(mock_client)

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_service] = lambda: service

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_health_check(test_app):
    response = test_app.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["portal_authenticated"] is True


def test_list_meters(test_app):
    response = test_app.get("/api/v1/meters")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] > 0
    assert data["page"] == 1
    assert len(data["items"]) <= 20


def test_search_meters_by_query(test_app):
    response = test_app.get("/api/v1/meters?q=J100000")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(m["id"] == "J100000" for m in data["items"])


def test_filter_meters_by_phase(test_app):
    response = test_app.get("/api/v1/meters?phase=single")
    assert response.status_code == 200
    data = response.json()
    for m in data["items"]:
        assert m["phase"] == "single"


def test_get_meter_detail(test_app):
    response = test_app.get("/api/v1/meters/J100000")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "J100000"
    assert "coordinates" in data
    assert "hierarchy" in data
    assert data["coordinates"]["latitude"] is not None


def test_get_meter_detail_not_found(test_app):
    response = test_app.get("/api/v1/meters/NONEXISTENT_999999")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "not_found"


def test_get_meter_consumption(test_app):
    response = test_app.get("/api/v1/meters/J100000/consumption?from=2026-06-25&to=2026-06-26")
    assert response.status_code == 200
    data = response.json()
    assert data["meter_id"] == "J100000"
    assert "summary" in data
    assert "readings" in data
    assert data["summary"]["total_consumption_kwh"] >= 0
    assert len(data["readings"]) > 0


def test_list_transformers(test_app):
    response = test_app.get("/api/v1/transformers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "code" in data[0]
    assert "assigned_meters_count" in data[0]


def test_get_transformer_detail(test_app):
    response = test_app.get("/api/v1/transformers/DT-001")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "DT-001"
    assert "meter_ids" in data
    assert isinstance(data["meter_ids"], list)


def test_get_transformer_not_found(test_app):
    response = test_app.get("/api/v1/transformers/NONEXISTENT_DT")
    assert response.status_code == 404


def test_get_grid_hierarchy(test_app):
    response = test_app.get("/api/v1/hierarchy")
    assert response.status_code == 200
    data = response.json()
    assert "zones" in data
    assert isinstance(data["zones"], list)


def test_trigger_sync(test_app):
    response = test_app.post("/api/v1/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "meters_synced" in data
