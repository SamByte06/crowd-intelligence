"""
Seed demo venue, gates, snapshots, and alerts for testing and evaluation.
"""

import sys
import uuid
from datetime import datetime, timezone, timedelta
from app.database import engine, Base, SessionLocal
from app.models import Venue, Gate, Alert, OccupancyBaseline, OccupancySnapshot
from app.models.gate import GateType, GateStatus, CameraSourceType
from app.models.alert import AlertSeverity, AlertStatus


def seed_demo_data():
    print("Initializing database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Check if already seeded
        existing_venue = db.query(Venue).filter(Venue.name.like("%Kashi Vishwanath%")).first()
        if existing_venue:
            print(f"Demo venue already exists: {existing_venue.name} (ID: {existing_venue.id})")
            return existing_venue.id

        print("Creating demo venue...")
        venue = Venue(
            id=str(uuid.uuid4()),
            name="Shri Kashi Vishwanath - Main Pilgrimage Corridor",
            description="High-footfall central corridor connecting Gate 4 (Dham) to the inner sanctum. Real-time crowd flow and bottleneck monitoring.",
            location="Varanasi, Uttar Pradesh",
            usable_area_sqm=650.0,
            max_capacity=1500,
            density_per_sqm=2.3,
            warning_threshold=0.75,
            critical_threshold=0.90,
            current_occupancy=620,
            total_entries=1450,
            total_exits=830,
            baseline_established=True,
            baseline_established_at=datetime.now(timezone.utc) - timedelta(hours=3),
            baseline_established_by="Duty Commander",
            timezone="Asia/Kolkata",
            is_active=True,
        )
        db.add(venue)
        db.flush()

        # Add Baseline record
        baseline = OccupancyBaseline(
            venue_id=venue.id,
            occupancy_value=120,
            established_by="Duty Commander",
            reason="Morning temple opening baseline verification",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        db.add(baseline)

        print("Creating gates...")
        gates = [
            Gate(
                id=str(uuid.uuid4()),
                venue_id=venue.id,
                display_name="Gate 1 — VIP / Northern Approach",
                gate_type=GateType.ENTRY,
                camera_source_type=CameraSourceType.WEBCAM,
                camera_source="0",
                line_start_x=0.05,
                line_start_y=0.55,
                line_end_x=0.95,
                line_end_y=0.55,
                counting_direction="down",
                confidence_threshold=0.25,
                frame_skip=1,
                is_enabled=True,
                status=GateStatus.ACTIVE,
                entry_count=820,
                exit_count=0,
                last_count_at=datetime.now(timezone.utc) - timedelta(seconds=12),
            ),
            Gate(
                id=str(uuid.uuid4()),
                venue_id=venue.id,
                display_name="Gate 2 — Ganga Ghat Pilgrimage Entry",
                gate_type=GateType.ENTRY,
                camera_source_type=CameraSourceType.HTTP,
                camera_source="http://192.168.1.102:8080/video",
                line_start_x=0.1,
                line_start_y=0.5,
                line_end_x=0.9,
                line_end_y=0.5,
                counting_direction="down",
                confidence_threshold=0.30,
                frame_skip=2,
                is_enabled=True,
                status=GateStatus.ACTIVE,
                entry_count=630,
                exit_count=0,
                last_count_at=datetime.now(timezone.utc) - timedelta(seconds=4),
            ),
            Gate(
                id=str(uuid.uuid4()),
                venue_id=venue.id,
                display_name="Gate 3 — Southern Exit Promenade",
                gate_type=GateType.EXIT,
                camera_source_type=CameraSourceType.WEBCAM,
                camera_source="1",
                line_start_x=0.1,
                line_start_y=0.45,
                line_end_x=0.9,
                line_end_y=0.45,
                counting_direction="up",
                confidence_threshold=0.25,
                frame_skip=1,
                is_enabled=True,
                status=GateStatus.ACTIVE,
                entry_count=0,
                exit_count=490,
                last_count_at=datetime.now(timezone.utc) - timedelta(seconds=8),
            ),
            Gate(
                id=str(uuid.uuid4()),
                venue_id=venue.id,
                display_name="Gate 4 — Western Plaza Exit",
                gate_type=GateType.EXIT,
                camera_source_type=CameraSourceType.RTSP,
                camera_source="rtsp://admin:pass@192.168.1.104:554/live",
                line_start_x=0.05,
                line_start_y=0.5,
                line_end_x=0.95,
                line_end_y=0.5,
                counting_direction="right",
                confidence_threshold=0.25,
                frame_skip=2,
                is_enabled=True,
                status=GateStatus.ACTIVE,
                entry_count=0,
                exit_count=340,
                last_count_at=datetime.now(timezone.utc) - timedelta(seconds=22),
            ),
        ]
        db.add_all(gates)

        print("Generating realistic time-series snapshots (past 60 minutes)...")
        now = datetime.now(timezone.utc)
        curr = 300
        total_in = 700
        total_out = 400

        for m in range(60, -1, -5):
            t = now - timedelta(minutes=m)
            in_step = 25 + (m % 7) * 3
            out_step = 16 + (m % 5) * 2
            total_in += in_step
            total_out += out_step
            curr += (in_step - out_step)
            curr = max(100, min(curr, 1400))

            snap = OccupancySnapshot(
                venue_id=venue.id,
                occupancy=curr,
                total_entries=total_in,
                total_exits=total_out,
                entry_rate=round(in_step / 5.0, 1),
                exit_rate=round(out_step / 5.0, 1),
                net_inflow=round((in_step - out_step) / 5.0, 1),
                capacity_utilization=round(curr / 1500.0, 3),
                timestamp=t,
            )
            db.add(snap)

        print("Creating sample alerts...")
        alerts = [
            Alert(
                id=str(uuid.uuid4()),
                venue_id=venue.id,
                severity=AlertSeverity.WARNING,
                status=AlertStatus.ACKNOWLEDGED,
                title="Approaching 75% Capacity Threshold",
                message="Occupancy in Main Pilgrimage Corridor has crossed 1,125 persons (75.0% capacity). Net inflow is +18 persons/min.",
                recommended_action="Direct upcoming queue to holding plaza 2; decelerate Gate 2 entry turnstiles.",
                occupancy_at_trigger=1130,
                capacity_at_trigger=1500,
                entry_rate_at_trigger=42.0,
                exit_rate_at_trigger=24.0,
                forecast_occupancy=1220,
                trigger_reason="warning_threshold_exceeded",
                triggered_at=now - timedelta(minutes=18),
                acknowledged_at=now - timedelta(minutes=14),
                acknowledged_by="Security Supervisor",
            ),
            Alert(
                id=str(uuid.uuid4()),
                venue_id=venue.id,
                severity=AlertSeverity.NORMAL,
                status=AlertStatus.RESOLVED,
                title="Morning Peak Flow Stabilized",
                message="Inflow and outflow rates normalized after morning Aarti ceremonies.",
                recommended_action="Resume standard entry cadence.",
                occupancy_at_trigger=680,
                capacity_at_trigger=1500,
                triggered_at=now - timedelta(hours=2),
                resolved_at=now - timedelta(hours=1, minutes=30),
                resolved_by="Security Supervisor",
                resolution_note="Queue clearance complete at 08:30 AM.",
            ),
        ]
        db.add_all(alerts)

        db.commit()
        print(f"Successfully seeded demo venue '{venue.name}'!")
        print(f"Venue ID: {venue.id}")
        return venue.id
    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
