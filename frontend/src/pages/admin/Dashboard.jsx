import { useState, useEffect } from "react";
import { Link, useOutletContext } from "react-router-dom";
import {
    fetchCrowdState,
    fetchEvents,
    getStoredEvents,
    clearStoredEvents,
} from "../../services/api";

function Dashboard() {
    const { formattedDateTime, liveCCTVTimestamp } = useOutletContext() || {
        formattedDateTime: "Mon, 21 Sep 2026   03:55 PM",
        liveCCTVTimestamp: "2026-09-21 15:55:00",
    };

    const [events, setEvents] = useState([]);
    const [crowdData, setCrowdData] = useState({
        total_people: 0,
        overall_risk: 0,
        overall_risk_level: "SAFE",
        zones: [
            { zone: 0, people: 0, risk_level: "SAFE" },
            { zone: 1, people: 0, risk_level: "SAFE" },
            { zone: 2, people: 0, risk_level: "SAFE" },
            { zone: 3, people: 0, risk_level: "SAFE" },
        ],
    });

    const [isFullscreen, setIsFullscreen] = useState(false);

    // Load registered events from storage / API
    const refreshEvents = async () => {
        const local = getStoredEvents();
        if (local && local.length > 0) {
            setEvents(local);
            return;
        }
        const apiRes = await fetchEvents();
        if (apiRes.events && apiRes.events.length > 0) {
            setEvents(apiRes.events);
        } else {
            setEvents([]);
        }
    };

    useEffect(() => {
        refreshEvents();
    }, []);

    // Poll live crowd state from AI backend when an event is active
    useEffect(() => {
        if (events.length === 0) return;

        let active = true;
        const loadCrowdData = async () => {
            const data = await fetchCrowdState();
            if (active && data) {
                setCrowdData(data);
            }
        };

        loadCrowdData();
        const timer = setInterval(loadCrowdData, 3000);
        return () => {
            active = false;
            clearInterval(timer);
        };
    }, [events.length]);

    const handleClearEvent = () => {
        if (window.confirm("Do you want to reset the active event?")) {
            clearStoredEvents();
            setEvents([]);
            setCrowdData({
                total_people: 0,
                overall_risk: 0,
                overall_risk_level: "SAFE",
                zones: [
                    { zone: 0, people: 0, risk_level: "SAFE" },
                    { zone: 1, people: 0, risk_level: "SAFE" },
                    { zone: 2, people: 0, risk_level: "SAFE" },
                    { zone: 3, people: 0, risk_level: "SAFE" },
                ],
            });
        }
    };

    const toggleFullscreen = () => {
        const feedElem = document.getElementById("camera-feed-box");
        if (!document.fullscreenElement && feedElem) {
            feedElem.requestFullscreen?.();
            setIsFullscreen(true);
        } else {
            document.exitFullscreen?.();
            setIsFullscreen(false);
        }
    };

    const hasActiveEvent = events.length > 0;
    const activeEvent = hasActiveEvent ? events[events.length - 1] : null;

    // Donut Gauge Calculations
    const gaugeRadius = 54;
    const gaugeCircumference = 2 * Math.PI * gaugeRadius;
    const riskPercent = crowdData.overall_risk || 0;
    const strokeDashoffset =
        gaugeCircumference - (riskPercent / 100) * gaugeCircumference;

    const riskLevelStr = (crowdData.overall_risk_level || "SAFE").toUpperCase();
    const isHighRisk = riskLevelStr === "HIGH" || riskLevelStr === "CRITICAL";
    const isModerateRisk = riskLevelStr === "MODERATE";

    return (
        <div className="admin-dashboard-view">
            {/* PAGE HEADER */}
            <div className="admin-page-header">
                <div>
                    <h1 className="page-title">Dashboard</h1>
                    <p className="page-subtitle">
                        Live monitoring and crowd risk analysis
                    </p>
                </div>
                <div className="page-datetime-stamp">{formattedDateTime}</div>
            </div>

            {/* IF NO EVENT REGISTERED: SHOW ONBOARDING CREATE EVENT VIEW */}
            {!hasActiveEvent ? (
                <div className="no-event-container">
                    {/* Main Empty State Card */}
                    <div className="empty-state-card">
                        <div className="empty-state-icon-circle">
                            <svg
                                width="36"
                                height="36"
                                viewBox="0 0 24 24"
                                fill="currentColor"
                            >
                                <path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zM9 14H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2zm-8 4H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2z" />
                            </svg>
                        </div>
                        <h2 className="empty-state-title">No Active Monitored Event</h2>
                        <p className="empty-state-desc">
                            There is currently no event registered for crowd intelligence and CCTV tracking.
                            Create an event to activate live camera monitoring, zone density detection, and AI crowd risk analysis.
                        </p>
                        <Link to="/admin/create-event" className="btn-create-event-primary-lg">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" />
                            </svg>
                            Create Event to Start Monitoring
                        </Link>
                    </div>

                    {/* 4-Step Onboarding Guidance Grid */}
                    <div className="empty-state-onboarding-grid">
                        <div className="onboarding-step-card">
                            <div className="onboarding-step-number">1</div>
                            <div className="onboarding-step-title">Create the Event</div>
                            <p className="onboarding-step-desc">
                                Register festival, stadium match, or public gathering with expected crowd volume.
                            </p>
                        </div>

                        <div className="onboarding-step-card">
                            <div className="onboarding-step-number">2</div>
                            <div className="onboarding-step-title">Add CCTV Cameras</div>
                            <p className="onboarding-step-desc">
                                Connect RTSP or IP entrance cameras covering major pedestrian gates and access points.
                            </p>
                        </div>

                        <div className="onboarding-step-card">
                            <div className="onboarding-step-number">3</div>
                            <div className="onboarding-step-title">Configure Zones</div>
                            <p className="onboarding-step-desc">
                                Map density zones (0-3) and threshold limits for automated early-warning triggers.
                            </p>
                        </div>

                        <div className="onboarding-step-card">
                            <div className="onboarding-step-number">4</div>
                            <div className="onboarding-step-title">Live AI Monitoring</div>
                            <p className="onboarding-step-desc">
                                Real-time YOLO person detection, ByteTrack tracking, and rush forecasting activate.
                            </p>
                        </div>
                    </div>
                </div>
            ) : (
                /* IF EVENT IS REGISTERED: SHOW MONITORING DASHBOARD */
                <>
                    {/* Active Event Banner */}
                    <div className="active-event-strip">
                        <div className="active-event-info">
                            <span className="active-event-pill">● ACTIVE EVENT</span>
                            <span className="active-event-name">{activeEvent.name}</span>
                            <span className="active-event-meta">📍 {activeEvent.location}</span>
                            <span className="active-event-meta">👥 Expected: {activeEvent.expected_crowd}</span>
                            <span className="active-event-meta">📅 {activeEvent.start_date} ({activeEvent.start_time})</span>
                        </div>
                        <div className="active-event-actions">
                            <Link to="/admin/create-event" className="btn-create-event-header" style={{ fontSize: "12px", padding: "5px 12px" }}>
                                + New Event
                            </Link>
                            <button className="btn-text-action" onClick={handleClearEvent}>
                                Reset Event
                            </button>
                        </div>
                    </div>

                    {/* TOP ROW: SECTION 1 (LIVE MONITORING) + SECTION 2 (ZONE DENSITY) */}
                    <div className="dashboard-top-grid">
                        {/* 1. LIVE MONITORING CARD */}
                        <div className="admin-card live-monitoring-card">
                            <div className="card-header-flex">
                                <div className="card-header-left">
                                    <h3>Live Monitoring</h3>
                                    <div className="camera-sub-indicator">
                                        <span className="dot-green" />
                                        <span>Camera 01 - Main Entrance</span>
                                    </div>
                                </div>

                                <div className="card-header-right">
                                    <div className="badge-live">
                                        <span className="badge-live-dot" />
                                        LIVE
                                    </div>
                                    <button
                                        className="btn-expand-icon"
                                        onClick={toggleFullscreen}
                                        title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
                                        aria-label="Expand camera view"
                                    >
                                        ⤢
                                    </button>
                                </div>
                            </div>

                            {/* Camera Feed Area */}
                            <div className="camera-feed-container" id="camera-feed-box">
                                <img
                                    src="https://suited-resources-anonymous-troy.trycloudflare.com/video_feed"
                                    alt="Live AI CCTV Crowd Monitoring"
                                    className="camera-feed-image"
                                />

                                {/* Top-Left Timestamp Overlay */}
                                <div className="camera-overlay-top-left">
                                    {liveCCTVTimestamp}
                                </div>

                                {/* Bottom-Left People Detected Overlay */}
                                <div className="camera-overlay-bottom-left">
                                    People Detected: {crowdData.total_people}
                                </div>
                            </div>
                        </div>

                        {/* 2. ZONE-WISE CROWD DENSITY (2x2 GRID) */}
                        <div className="admin-card zone-density-container-card">
                            <div className="card-header-flex">
                                <div className="card-header-left">
                                    <h3>Zone-wise Crowd Density</h3>
                                </div>
                            </div>

                            <div className="zones-2x2-grid">
                                {(crowdData.zones || [0, 1, 2, 3]).map((z, idx) => {
                                    const zNumber = typeof z === "object" ? z.zone ?? idx : idx;
                                    const zPeople = typeof z === "object" ? z.people ?? 0 : 0;
                                    const zLevel = typeof z === "object" ? z.risk_level || "SAFE" : "SAFE";
                                    const zClass = zLevel.toLowerCase();

                                    const iconColor =
                                        zClass === "high" || zClass === "critical"
                                            ? "#EF4444"
                                            : zClass === "moderate"
                                            ? "#F59E0B"
                                            : "#10B981";

                                    return (
                                        <div key={idx} className={`zone-density-card risk-${zClass}`}>
                                            <div className="zone-card-top">Zone {zNumber}</div>
                                            <div className="zone-card-middle">
                                                <span className="zone-people-icon" style={{ color: iconColor }}>
                                                    <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
                                                        <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" />
                                                    </svg>
                                                </span>
                                                <div className="zone-count-group">
                                                    <span className="zone-people-number">
                                                        {zPeople}
                                                    </span>
                                                    <span className="zone-people-label">people</span>
                                                </div>
                                            </div>
                                            <div>
                                                <span className={`zone-badge ${zClass}`}>
                                                    {zLevel}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                    {/* BOTTOM ROW: SECTION 3 (OVERALL RISK LEVEL) */}
                    <div className="overall-risk-card">
                        <h3>Overall Risk Level</h3>

                        <div className="risk-level-flex">
                            {/* Donut Gauge */}
                            <div className="circular-gauge-wrapper">
                                <svg className="circular-gauge-svg" viewBox="0 0 140 140">
                                    {/* Track */}
                                    <circle
                                        className="gauge-bg-track"
                                        cx="70"
                                        cy="70"
                                        r={gaugeRadius}
                                    />
                                    {/* Progress Arc */}
                                    <circle
                                        className={`gauge-progress-arc ${
                                            isHighRisk ? "risk-high" : isModerateRisk ? "risk-moderate" : ""
                                        }`}
                                        cx="70"
                                        cy="70"
                                        r={gaugeRadius}
                                        strokeDasharray={gaugeCircumference}
                                        strokeDashoffset={strokeDashoffset}
                                    />
                                </svg>
                                <div className="gauge-center-text">
                                    <span className="gauge-score-number">
                                        {crowdData.overall_risk ?? 0}
                                    </span>
                                    <span className="gauge-max-number">/ 100</span>
                                </div>
                            </div>

                            {/* Divider */}
                            <div className="risk-level-divider" />

                            {/* Risk Details */}
                            <div className="risk-level-details">
                                <span className="risk-level-tag">RISK LEVEL</span>
                                <div
                                    className={`risk-level-state-title ${
                                        isHighRisk ? "risk-high" : isModerateRisk ? "risk-moderate" : ""
                                    }`}
                                >
                                    {riskLevelStr}
                                </div>
                                <p className="risk-desc-line">
                                    {crowdData.alert ||
                                        (isHighRisk
                                            ? "Crowd density is above normal. Monitor closely."
                                            : "Crowd density is within safe operational limits.")}
                                </p>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}

export default Dashboard;
