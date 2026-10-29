"""
Complete system verification suite (no external test runner required).
Runs unit tests, service tests, and API integration tests.
"""

import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.venue import Venue
from app.models.gate import Gate, GateType, GateStatus, CameraSourceType
from app.models.counting_event import CountingEvent, CrossingDirection
from app.services.gate_counter import GateCounter, LineCrossingConfig
from app.services.occupancy_service import OccupancyService
from app.services.flow_service import FlowRateService
from app.services.forecast_service import ForecastService
from app.services.alert_service import AlertService
from app.main import app
from fastapi.testclient import TestClient


passed = 0
failed = 0


def test(name):
    """Decorator to run and report test."""
    def decorator(fn):
        global passed, failed
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
        return fn
    return decorator


print("=" * 60)
print("1. RUNNING GATE COUNTER (VIRTUAL LINE CROSSING) TESTS")
print("=" * 60)


@test("Entry crossing: Top to bottom (counting_direction='down')")
def _():
    cfg = LineCrossingConfig(start_x=0.0, start_y=0.5, end_x=1.0, end_y=0.5, counting_direction="down")
    counter = GateCounter(cfg)
    now = time.time()
    ev1 = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now)
    assert len(ev1) == 0, f"Expected 0, got {len(ev1)}"
    ev2 = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.7}], now + 0.5)
    assert len(ev2) == 1, f"Expected 1, got {len(ev2)}"
    assert ev2[0].direction == "IN", f"Expected IN, got {ev2[0].direction}"


@test("Exit crossing: Bottom to top (counting_direction='down')")
def _():
    cfg = LineCrossingConfig(start_x=0.0, start_y=0.5, end_x=1.0, end_y=0.5, counting_direction="down")
    counter = GateCounter(cfg)
    now = time.time()
    counter.update([{"track_id": 2, "cx": 0.5, "cy": 0.7}], now)
    ev = counter.update([{"track_id": 2, "cx": 0.5, "cy": 0.3}], now + 0.5)
    assert len(ev) == 1
    assert ev[0].direction == "OUT"


@test("Horizontal line crossing: Left to right (counting_direction='right')")
def _():
    cfg = LineCrossingConfig(start_x=0.5, start_y=0.0, end_x=0.5, end_y=1.0, counting_direction="right")
    counter = GateCounter(cfg)
    now = time.time()
    counter.update([{"track_id": 3, "cx": 0.3, "cy": 0.5}], now)
    ev = counter.update([{"track_id": 3, "cx": 0.7, "cy": 0.5}], now + 0.5)
    assert len(ev) == 1
    assert ev[0].direction == "IN"


@test("Duplicate crossing prevention within cooldown window")
def _():
    cfg = LineCrossingConfig(start_x=0.0, start_y=0.5, end_x=1.0, end_y=0.5, crossing_cooldown=2.0)
    counter = GateCounter(cfg)
    now = time.time()
    counter.update([{"track_id": 4, "cx": 0.5, "cy": 0.3}], now)
    ev1 = counter.update([{"track_id": 4, "cx": 0.5, "cy": 0.7}], now + 0.1)
    assert len(ev1) == 1
    # Jitter across line within cooldown
    counter.update([{"track_id": 4, "cx": 0.5, "cy": 0.4}], now + 0.2)
    ev2 = counter.update([{"track_id": 4, "cx": 0.5, "cy": 0.7}], now + 0.3)
    assert len(ev2) == 0, "Duplicate crossing was not prevented!"


@test("Track cleanup after expiry")
def _():
    cfg = LineCrossingConfig(track_expiry=0.2)
    counter = GateCounter(cfg)
    now = time.time()
    counter.update([{"track_id": 5, "cx": 0.5, "cy": 0.2}], now)
    assert 5 in counter._tracks
    counter.cleanup_tracks(now + 1.0)
    assert 5 not in counter._tracks


print("\n" + "=" * 60)
print("2. RUNNING OCCUPANCY, FLOW & ALERT SERVICES TESTS")
print("=" * 60)


def create_in_memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


@test("Occupancy calculation with baseline + crossings")
def _():
    db = create_in_memory_db()
    v = Venue(id="v1", name="Hall A", max_capacity=500)
    g = Gate(id="g1", venue_id="v1", display_name="Gate 1", gate_type=GateType.ENTRY)
    db.add_all([v, g])
    db.commit()

    OccupancyService.set_baseline(db, "v1", 50, "admin", "Initial shift count")
    assert v.current_occupancy == 50

    # Record 3 entries and 1 exit
    OccupancyService.record_crossing(db, "v1", "g1", "IN", 101, 0.9)
    OccupancyService.record_crossing(db, "v1", "g1", "IN", 102, 0.9)
    OccupancyService.record_crossing(db, "v1", "g1", "IN", 103, 0.9)
    OccupancyService.record_crossing(db, "v1", "g1", "OUT", 104, 0.9)

    state = OccupancyService.get_occupancy(db, "v1")
    assert state["current_occupancy"] == 52, f"Expected 52, got {state['current_occupancy']}"
    assert state["total_entries"] == 3
    assert state["total_exits"] == 1


@test("Flow rate calculation and windowing")
def _():
    db = create_in_memory_db()
    v = Venue(id="v2", name="Hall B", max_capacity=1000)
    g = Gate(id="g2", venue_id="v2", display_name="Gate 2", gate_type=GateType.ENTRY)
    db.add_all([v, g])
    db.commit()

    # Add 12 entries in the last 60 seconds
    now = datetime.now(timezone.utc)
    for i in range(12):
        ev = CountingEvent(
            venue_id="v2", gate_id="g2", direction=CrossingDirection.IN,
            track_id=i, timestamp=now - timedelta(seconds=i * 4),
        )
        db.add(ev)
    db.commit()

    flow = FlowRateService.calculate(db, "v2", window_seconds=60)
    assert flow["total_entries_in_window"] == 12
    assert flow["entry_rate_per_min"] == 12.0
    assert flow["net_inflow_per_min"] == 12.0


@test("Capacity forecast and time-to-warning ETA")
def _():
    db = create_in_memory_db()
    v = Venue(
        id="v3", name="Hall C", max_capacity=200,
        warning_threshold=0.8, critical_threshold=0.9,
        current_occupancy=140,  # Warning is at 160 (20 persons away)
    )
    g = Gate(id="g3", venue_id="v3", display_name="Gate 3", gate_type=GateType.ENTRY)
    db.add_all([v, g])
    db.commit()

    now = datetime.now(timezone.utc)
    # Net inflow of 10 persons/min (10 entries in 60s)
    for i in range(10):
        ev = CountingEvent(
            venue_id="v3", gate_id="g3", direction=CrossingDirection.IN,
            track_id=i, timestamp=now - timedelta(seconds=i * 5),
        )
        db.add(ev)
    db.commit()

    fc = ForecastService.forecast(db, "v3")
    assert fc["current_occupancy"] == 140
    # Time to reach 160 at 10/min is ~2.0 minutes
    assert fc["time_to_warning_minutes"] is not None
    assert 1.5 <= fc["time_to_warning_minutes"] <= 2.5, f"Got {fc['time_to_warning_minutes']}"


@test("Alert generation on threshold breach")
def _():
    db = create_in_memory_db()
    v = Venue(
        id="v4", name="Hall D", max_capacity=100,
        warning_threshold=0.7, critical_threshold=0.9,
        current_occupancy=95,  # 95% -> CRITICAL
    )
    db.add(v)
    db.commit()

    alerts = AlertService.evaluate(db, "v4")
    assert len(alerts) >= 1
    assert any(a.severity.value == "CRITICAL" for a in alerts)


print("\n" + "=" * 60)
print("3. RUNNING REST API INTEGRATION TESTS")
print("=" * 60)

import os
if os.environ.get("SKIP_API_TESTCLIENT") == "1":
    print("  [INFO] Skipping TestClient tests in sandbox mode (requires network loopback for AnyIO portal)")
else:
    client = TestClient(app)


    @test("API: GET /api/v1/health")
    def _():
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"


    @test("API: POST & GET /api/v1/venues")
    def _():
        venue_payload = {
            "name": "Integration Test Arena",
            "description": "Auto-test venue",
            "max_capacity": 500,
            "warning_threshold": 0.75,
            "critical_threshold": 0.90,
        }
        create_res = client.post("/api/v1/venues", json=venue_payload)
        assert create_res.status_code == 201
        v_id = create_res.json()["id"]

        get_res = client.get(f"/api/v1/venues/{v_id}")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Integration Test Arena"


    @test("API: Full Dashboard endpoint")
    def _():
        venues = client.get("/api/v1/venues").json()
        assert len(venues) > 0
        v_id = venues[0]["id"]
        dash_res = client.get(f"/api/v1/venues/{v_id}/dashboard")
        assert dash_res.status_code == 200
        data = dash_res.json()
        assert "occupancy" in data
        assert "flow" in data
        assert "forecast" in data
        assert "alerts" in data
        assert "gates" in data


print("\n" + "=" * 60)
print(f"VERIFICATION SUMMARY: {passed} PASSED, {failed} FAILED")
print("=" * 60)

if failed > 0:
    sys.exit(1)
