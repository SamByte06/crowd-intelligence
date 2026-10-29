"""
Integration tests for the FastAPI application.

Tests the full API request/response cycle with a test database.
"""

import os
os.environ["TESTING"] = "1"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture(scope="module")
def test_db():
    """Create a persistent in-memory test database shared across connections."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def client(test_db):
    """FastAPI test client."""
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestVenueAPI:
    def test_create_venue(self, client):
        resp = client.post("/api/v1/venues", json={
            "name": "Ram Mandir",
            "description": "Temple complex",
            "usable_area_sqm": 5000.0,
            "max_capacity": 1000,
            "warning_threshold": 0.75,
            "critical_threshold": 0.90,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Ram Mandir"
        assert data["max_capacity"] == 1000
        assert data["effective_capacity"] == 1000
        assert data["capacity_is_estimated"] is False
        return data["id"]

    def test_list_venues(self, client):
        resp = client.get("/api/v1/venues")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_venue(self, client):
        # Create first
        create_resp = client.post("/api/v1/venues", json={
            "name": "Test Venue",
            "max_capacity": 500,
        })
        venue_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/venues/{venue_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Venue"

    def test_update_venue(self, client):
        create_resp = client.post("/api/v1/venues", json={"name": "To Update"})
        venue_id = create_resp.json()["id"]

        resp = client.patch(f"/api/v1/venues/{venue_id}", json={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_set_baseline(self, client):
        create_resp = client.post("/api/v1/venues", json={
            "name": "Baseline Test",
            "max_capacity": 1000,
        })
        venue_id = create_resp.json()["id"]

        resp = client.post(f"/api/v1/venues/{venue_id}/baseline", json={
            "occupancy": 650,
            "established_by": "admin",
            "reason": "Manual headcount",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_occupancy"] == 650
        assert data["baseline_established"] is True

    def test_venue_not_found(self, client):
        resp = client.get("/api/v1/venues/nonexistent")
        assert resp.status_code == 404

    def test_invalid_thresholds(self, client):
        resp = client.post("/api/v1/venues", json={
            "name": "Bad Venue",
            "warning_threshold": 0.90,
            "critical_threshold": 0.75,  # Must be > warning
        })
        assert resp.status_code == 422

    def test_process_lifecycle(self, client):
        venue_resp = client.post("/api/v1/venues", json={"name": "Process Test Venue", "max_capacity": 500})
        venue_id = venue_resp.json()["id"]

        # 1. Start Process
        start_resp = client.post(f"/api/v1/venues/{venue_id}/start-process")
        assert start_resp.status_code == 200
        assert start_resp.json()["monitoring_active"] is True

        # 2. Pause Process
        pause_resp = client.post(f"/api/v1/venues/{venue_id}/pause-process")
        assert pause_resp.status_code == 200
        assert pause_resp.json()["monitoring_active"] is False

        # 3. Reset Process
        reset_resp = client.post(f"/api/v1/venues/{venue_id}/reset-process")
        assert reset_resp.status_code == 200
        assert reset_resp.json()["monitoring_active"] is False

    def test_delete_venue(self, client):
        venue_resp = client.post("/api/v1/venues", json={"name": "Venue To Delete"})
        venue_id = venue_resp.json()["id"]

        del_resp = client.delete(f"/api/v1/venues/{venue_id}")
        assert del_resp.status_code == 204

        get_resp = client.get(f"/api/v1/venues/{venue_id}")
        assert get_resp.status_code == 404


class TestGateAPI:
    def test_create_gate(self, client):
        venue_resp = client.post("/api/v1/venues", json={"name": "Gate Test Venue"})
        venue_id = venue_resp.json()["id"]

        resp = client.post(f"/api/v1/venues/{venue_id}/gates", json={
            "display_name": "Entry Gate 1",
            "gate_type": "ENTRY",
            "camera_source_type": "WEBCAM",
            "camera_source": "0",
            "counting_direction": "down",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_name"] == "Entry Gate 1"
        assert data["gate_type"] == "ENTRY"
        # Credentials should NOT be in response
        assert "camera_username" not in data
        assert "camera_password" not in data

    def test_list_gates(self, client):
        venue_resp = client.post("/api/v1/venues", json={"name": "List Gate Venue"})
        venue_id = venue_resp.json()["id"]

        client.post(f"/api/v1/venues/{venue_id}/gates", json={
            "display_name": "Gate A",
            "gate_type": "ENTRY",
        })
        client.post(f"/api/v1/venues/{venue_id}/gates", json={
            "display_name": "Gate B",
            "gate_type": "EXIT",
        })

        resp = client.get(f"/api/v1/venues/{venue_id}/gates")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_update_gate(self, client):
        venue_resp = client.post("/api/v1/venues", json={"name": "Update Gate Venue"})
        venue_id = venue_resp.json()["id"]

        gate_resp = client.post(f"/api/v1/venues/{venue_id}/gates", json={
            "display_name": "Old Name",
            "gate_type": "ENTRY",
        })
        gate_id = gate_resp.json()["id"]

        resp = client.patch(f"/api/v1/gates/{gate_id}", json={
            "display_name": "New Name",
        })
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "New Name"

    def test_delete_gate(self, client):
        venue_resp = client.post("/api/v1/venues", json={"name": "Delete Gate Venue"})
        venue_id = venue_resp.json()["id"]

        gate_resp = client.post(f"/api/v1/venues/{venue_id}/gates", json={
            "display_name": "To Delete",
            "gate_type": "EXIT",
        })
        gate_id = gate_resp.json()["id"]

        resp = client.delete(f"/api/v1/gates/{gate_id}")
        assert resp.status_code == 204

    def test_start_gate_requires_baseline(self, client):
        venue_resp = client.post("/api/v1/venues", json={"name": "No Baseline Venue"})
        venue_id = venue_resp.json()["id"]

        gate_resp = client.post(f"/api/v1/venues/{venue_id}/gates", json={
            "display_name": "Gate",
            "gate_type": "ENTRY",
        })
        gate_id = gate_resp.json()["id"]

        resp = client.post(f"/api/v1/gates/{gate_id}/start")
        assert resp.status_code == 400
        assert "baseline" in resp.json()["detail"].lower()


class TestMonitoringAPI:
    def test_occupancy_endpoint(self, client):
        venue_resp = client.post("/api/v1/venues", json={
            "name": "Monitor Venue",
            "max_capacity": 1000,
        })
        venue_id = venue_resp.json()["id"]

        client.post(f"/api/v1/venues/{venue_id}/baseline", json={
            "occupancy": 500,
            "established_by": "admin",
        })

        resp = client.get(f"/api/v1/venues/{venue_id}/occupancy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_occupancy"] == 500
        assert data["occupancy_percentage"] == 50.0

    def test_flow_endpoint(self, client):
        venue_resp = client.post("/api/v1/venues", json={"name": "Flow Venue"})
        venue_id = venue_resp.json()["id"]

        resp = client.get(f"/api/v1/venues/{venue_id}/flow")
        assert resp.status_code == 200
        data = resp.json()
        assert "entry_rate_per_min" in data

    def test_forecast_endpoint(self, client):
        venue_resp = client.post("/api/v1/venues", json={
            "name": "Forecast Venue",
            "max_capacity": 1000,
        })
        venue_id = venue_resp.json()["id"]

        resp = client.get(f"/api/v1/venues/{venue_id}/forecast")
        assert resp.status_code == 200
        data = resp.json()
        assert "forecasts" in data
        assert "data_quality" in data

    def test_alerts_endpoint(self, client):
        venue_resp = client.post("/api/v1/venues", json={"name": "Alert Venue"})
        venue_id = venue_resp.json()["id"]

        resp = client.get(f"/api/v1/venues/{venue_id}/alerts")
        assert resp.status_code == 200

    def test_camera_health_endpoint(self, client):
        resp = client.get("/api/v1/cameras/health")
        assert resp.status_code == 200
