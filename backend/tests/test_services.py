"""
Tests for occupancy, flow, forecast, and alert services.

Uses an in-memory SQLite database for isolation.
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.venue import Venue
from app.models.gate import Gate, GateType, GateStatus, CameraSourceType
from app.models.counting_event import CountingEvent, CrossingDirection
from app.services.occupancy_service import OccupancyService
from app.services.flow_service import FlowRateService
from app.services.forecast_service import ForecastService
from app.services.alert_service import AlertService


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def venue(db_session):
    """Create a test venue."""
    v = Venue(
        id=str(uuid.uuid4()),
        name="Test Venue",
        usable_area_sqm=500.0,
        max_capacity=1000,
        warning_threshold=0.75,
        critical_threshold=0.90,
    )
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)
    return v


@pytest.fixture
def entry_gate(db_session, venue):
    """Create a test entry gate."""
    g = Gate(
        id=str(uuid.uuid4()),
        venue_id=venue.id,
        display_name="Entry Gate 1",
        gate_type=GateType.ENTRY,
        camera_source_type=CameraSourceType.WEBCAM,
        camera_source="0",
        status=GateStatus.ACTIVE,
    )
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


@pytest.fixture
def exit_gate(db_session, venue):
    """Create a test exit gate."""
    g = Gate(
        id=str(uuid.uuid4()),
        venue_id=venue.id,
        display_name="Exit Gate 1",
        gate_type=GateType.EXIT,
        camera_source_type=CameraSourceType.WEBCAM,
        camera_source="0",
        status=GateStatus.ACTIVE,
    )
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


class TestOccupancyService:
    """Tests for occupancy calculations."""

    def test_set_baseline(self, db_session, venue):
        """Setting baseline should update venue occupancy."""
        updated = OccupancyService.set_baseline(db_session, venue.id, 650, "admin", "Initial count")
        assert updated.current_occupancy == 650
        assert updated.baseline_established is True
        assert updated.total_entries == 0
        assert updated.total_exits == 0

    def test_baseline_rejects_negative(self, db_session, venue):
        """Negative baseline should be rejected."""
        with pytest.raises(ValueError, match="negative"):
            OccupancyService.set_baseline(db_session, venue.id, -10)

    def test_record_entry_crossing(self, db_session, venue, entry_gate):
        """Entry crossing should increment occupancy and entry count."""
        OccupancyService.set_baseline(db_session, venue.id, 100)

        event = OccupancyService.record_crossing(
            db_session, venue.id, entry_gate.id, "IN", track_id=1
        )
        assert event.direction == CrossingDirection.IN

        db_session.refresh(venue)
        assert venue.current_occupancy == 101
        assert venue.total_entries == 1

    def test_record_exit_crossing(self, db_session, venue, exit_gate):
        """Exit crossing should decrement occupancy and increment exit count."""
        OccupancyService.set_baseline(db_session, venue.id, 100)

        OccupancyService.record_crossing(
            db_session, venue.id, exit_gate.id, "OUT", track_id=2
        )

        db_session.refresh(venue)
        assert venue.current_occupancy == 99
        assert venue.total_exits == 1

    def test_occupancy_calculation(self, db_session, venue, entry_gate, exit_gate):
        """Occupancy = baseline + entries - exits."""
        OccupancyService.set_baseline(db_session, venue.id, 500)

        # 10 entries
        for i in range(10):
            OccupancyService.record_crossing(
                db_session, venue.id, entry_gate.id, "IN", track_id=100 + i
            )

        # 3 exits
        for i in range(3):
            OccupancyService.record_crossing(
                db_session, venue.id, exit_gate.id, "OUT", track_id=200 + i
            )

        db_session.refresh(venue)
        assert venue.current_occupancy == 507  # 500 + 10 - 3
        assert venue.total_entries == 10
        assert venue.total_exits == 3

    def test_get_occupancy(self, db_session, venue):
        """Get occupancy should return correct percentages."""
        OccupancyService.set_baseline(db_session, venue.id, 750)
        data = OccupancyService.get_occupancy(db_session, venue.id)

        assert data["current_occupancy"] == 750
        assert data["effective_capacity"] == 1000
        assert data["remaining_capacity"] == 250
        assert data["occupancy_percentage"] == 75.0

    def test_reconcile(self, db_session, venue):
        """Reconciliation should update occupancy to verified value."""
        OccupancyService.set_baseline(db_session, venue.id, 500)
        OccupancyService.reconcile(db_session, venue.id, 480, "admin", "Manual headcount")

        db_session.refresh(venue)
        assert venue.current_occupancy == 480

    def test_estimated_capacity(self, db_session):
        """Venue without max_capacity should use area-based estimate."""
        v = Venue(
            id=str(uuid.uuid4()),
            name="Estimated Venue",
            usable_area_sqm=500.0,
            max_capacity=None,
            density_per_sqm=2.0,
        )
        db_session.add(v)
        db_session.commit()
        db_session.refresh(v)

        assert v.effective_capacity == 1000
        assert v.capacity_is_estimated is True


class TestFlowRateService:
    """Tests for flow rate calculations."""

    def test_flow_rates_with_events(self, db_session, venue, entry_gate, exit_gate):
        """Flow rates should be calculated from counting events."""
        now = datetime.now(timezone.utc)

        # Add events within last minute
        for i in range(6):
            db_session.add(CountingEvent(
                venue_id=venue.id,
                gate_id=entry_gate.id,
                direction=CrossingDirection.IN,
                timestamp=now - timedelta(seconds=i * 5),
            ))

        for i in range(2):
            db_session.add(CountingEvent(
                venue_id=venue.id,
                gate_id=exit_gate.id,
                direction=CrossingDirection.OUT,
                timestamp=now - timedelta(seconds=i * 10),
            ))
        db_session.commit()

        flow = FlowRateService.calculate(db_session, venue.id, 60)
        assert flow["total_entries_in_window"] == 6
        assert flow["total_exits_in_window"] == 2
        assert flow["entry_rate_per_min"] == 6.0
        assert flow["exit_rate_per_min"] == 2.0
        assert flow["net_inflow_per_min"] == 4.0

    def test_empty_window(self, db_session, venue):
        """Empty window should return zero rates."""
        flow = FlowRateService.calculate(db_session, venue.id, 60)
        assert flow["entry_rate_per_min"] == 0
        assert flow["exit_rate_per_min"] == 0
        assert flow["net_inflow_per_min"] == 0


class TestForecastService:
    """Tests for occupancy forecasting."""

    def test_positive_net_inflow_forecast(self, db_session, venue, entry_gate):
        """Positive inflow should project increasing occupancy."""
        OccupancyService.set_baseline(db_session, venue.id, 500)
        now = datetime.now(timezone.utc)

        # Add entry events to create positive inflow
        for i in range(10):
            db_session.add(CountingEvent(
                venue_id=venue.id,
                gate_id=entry_gate.id,
                direction=CrossingDirection.IN,
                timestamp=now - timedelta(seconds=i * 3),
            ))
        db_session.commit()

        forecast = ForecastService.forecast(db_session, venue.id)
        assert forecast["current_occupancy"] == 500
        assert forecast["net_inflow_rate"] > 0

        # All forecast points should be >= current
        for f in forecast["forecasts"]:
            assert f["forecast_occupancy"] >= 500

    def test_zero_inflow_no_time_to_capacity(self, db_session, venue):
        """Zero net inflow should not produce time-to-capacity."""
        OccupancyService.set_baseline(db_session, venue.id, 500)
        forecast = ForecastService.forecast(db_session, venue.id)

        assert forecast["time_to_warning_minutes"] is None
        assert forecast["time_to_capacity_minutes"] is None

    def test_negative_inflow_forecast(self, db_session, venue, exit_gate):
        """Negative inflow should project decreasing occupancy."""
        OccupancyService.set_baseline(db_session, venue.id, 500)
        now = datetime.now(timezone.utc)

        for i in range(10):
            db_session.add(CountingEvent(
                venue_id=venue.id,
                gate_id=exit_gate.id,
                direction=CrossingDirection.OUT,
                timestamp=now - timedelta(seconds=i * 3),
            ))
        db_session.commit()

        forecast = ForecastService.forecast(db_session, venue.id)
        assert forecast["net_inflow_rate"] < 0
        assert forecast["time_to_capacity_minutes"] is None

    def test_data_quality_insufficient(self, db_session, venue):
        """No enabled gates should report insufficient data quality."""
        forecast = ForecastService.forecast(db_session, venue.id)
        assert forecast["data_quality"] == "insufficient"


class TestAlertService:
    """Tests for alert evaluation and lifecycle."""

    def test_warning_alert_created(self, db_session, venue, entry_gate):
        """Warning alert should fire when occupancy crosses warning threshold."""
        OccupancyService.set_baseline(db_session, venue.id, 760)  # 76% > 75% warning

        alerts = AlertService.evaluate(db_session, venue.id)
        warning_alerts = [a for a in alerts if a.severity.value == "WARNING"]
        assert len(warning_alerts) >= 1

    def test_critical_alert_created(self, db_session, venue, entry_gate):
        """Critical alert should fire when occupancy crosses critical threshold."""
        OccupancyService.set_baseline(db_session, venue.id, 920)  # 92% > 90% critical

        alerts = AlertService.evaluate(db_session, venue.id)
        critical_alerts = [a for a in alerts if a.severity.value == "CRITICAL"]
        assert len(critical_alerts) >= 1

    def test_alert_deduplication(self, db_session, venue, entry_gate):
        """Same alert should not be created twice while active."""
        OccupancyService.set_baseline(db_session, venue.id, 920)

        alerts1 = AlertService.evaluate(db_session, venue.id)
        alerts2 = AlertService.evaluate(db_session, venue.id)

        # Second evaluation should not create new alerts
        assert len(alerts2) == 0

    def test_acknowledge_alert(self, db_session, venue, entry_gate):
        """Alert acknowledgement should update status."""
        OccupancyService.set_baseline(db_session, venue.id, 920)
        alerts = AlertService.evaluate(db_session, venue.id)
        assert len(alerts) > 0

        acked = AlertService.acknowledge(db_session, alerts[0].id, "operator1")
        assert acked.status.value == "ACKNOWLEDGED"
        assert acked.acknowledged_by == "operator1"

    def test_resolve_alert(self, db_session, venue, entry_gate):
        """Alert resolution should update status and record note."""
        OccupancyService.set_baseline(db_session, venue.id, 920)
        alerts = AlertService.evaluate(db_session, venue.id)

        resolved = AlertService.resolve(
            db_session, alerts[0].id, "admin", "Crowd dispersed"
        )
        assert resolved.status.value == "RESOLVED"
        assert resolved.resolution_note == "Crowd dispersed"

    def test_no_alert_below_threshold(self, db_session, venue, entry_gate):
        """No occupancy alert should fire when below warning threshold."""
        OccupancyService.set_baseline(db_session, venue.id, 500)  # 50%
        alerts = AlertService.evaluate(db_session, venue.id)
        occupancy_alerts = [
            a for a in alerts
            if "occupancy" in (a.alert_type_key or "")
        ]
        assert len(occupancy_alerts) == 0
