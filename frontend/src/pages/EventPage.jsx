import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { fetchCrowdState, fetchEvents, getStoredEvents } from "../services/api";

function RiskBadge({ level }) {
    const riskLevel = level || "WAITING";

    return (
        <span className={`risk-badge risk-${riskLevel.toLowerCase()}`}>
            {riskLevel}
        </span>
    );
}

function EventPage() {
    const { eventId } = useParams();
    const navigate = useNavigate();

    const [event, setEvent] = useState(null);
    const [crowd, setCrowd] = useState(null);
    const [loading, setLoading] = useState(true);

    // Fetch Event Details
    useEffect(() => {
        const loadEvent = async () => {
            const localEvents = getStoredEvents();
            let found = localEvents.find((e) => String(e.id) === String(eventId));

            if (!found) {
                try {
                    const res = await fetchEvents();
                    if (res.events) {
                        found = res.events.find((e) => String(e.id) === String(eventId));
                    }
                } catch (err) {
                    console.error("Failed to fetch event:", err);
                }
            }

            // Fallback if accessed by index or generic id
            if (!found && localEvents.length > 0) {
                found = localEvents[0];
            }

            setEvent(found || null);
            setLoading(false);
        };

        loadEvent();
    }, [eventId]);

    // Poll Live Crowd Intelligence
    useEffect(() => {
        let active = true;

        const loadCrowd = async () => {
            try {
                const data = await fetchCrowdState();
                if (active && data) {
                    setCrowd(data);
                }
            } catch (error) {
                console.log("Crowd data unavailable");
            }
        };

        loadCrowd();
        const interval = setInterval(loadCrowd, 2000);

        return () => {
            active = false;
            clearInterval(interval);
        };
    }, []);

    if (loading) {
        return (
            <div className="section not-found">
                <h2>Loading Event Intelligence...</h2>
            </div>
        );
    }

    if (!event) {
        return (
            <>
                <nav className="navbar">
                    <Link to="/" className="logo">
                        AI Crowd Intelligence
                    </Link>
                    <div className="nav-links">
                        <Link to="/">Home</Link>
                        <Link to="/admin" className="nav-link-button">
                            Admin
                        </Link>
                    </div>
                </nav>

                <div className="section not-found">
                    <button className="back-button" onClick={() => navigate("/")}>
                        ← Back to Home
                    </button>
                    <h2>Event Not Found</h2>
                    <p style={{ marginTop: "10px", color: "#64748b" }}>
                        The requested event could not be found or has been completed.
                    </p>
                </div>
            </>
        );
    }

    const zones = crowd?.zones || [
        { zone: 0, people: 0, density: "LOW", dominant_direction: "STATIONARY", trend: "STABLE", congestion: "LOW", risk: 0, risk_level: "SAFE" },
        { zone: 1, people: 0, density: "LOW", dominant_direction: "STATIONARY", trend: "STABLE", congestion: "LOW", risk: 0, risk_level: "SAFE" },
        { zone: 2, people: 0, density: "LOW", dominant_direction: "STATIONARY", trend: "STABLE", congestion: "LOW", risk: 0, risk_level: "SAFE" },
        { zone: 3, people: 0, density: "LOW", dominant_direction: "STATIONARY", trend: "STABLE", congestion: "LOW", risk: 0, risk_level: "SAFE" },
    ];

    return (
        <>
            <nav className="navbar">
                <Link to="/" className="logo">
                    AI Crowd Intelligence
                </Link>

                <div className="nav-links">
                    <Link to="/">Home</Link>
                    <Link to="/admin" className="nav-link-button">
                        Admin
                    </Link>
                </div>
            </nav>

            <main>
                {/* Event Hero Header */}
                <section className="event-hero-section">
                    <div className="event-hero-inner">
                        <button className="back-button" onClick={() => navigate("/")}>
                            ← Back to Home
                        </button>

                        <div className="event-hero-meta">
                            <span className="event-type-badge">{event.type || "Public Event"}</span>
                            <span className={`event-status-pill ${String(event.status || "Active").toLowerCase()}`}>
                                ● {event.status || "Active"}
                            </span>
                        </div>

                        <h1>{event.name}</h1>
                        <p className="place-location">📍 {event.location}</p>

                        <div className="event-hero-details-row">
                            <div className="event-hero-detail">
                                <strong>Expected Attendees</strong>
                                <span>
                                    {event.expected_crowd
                                        ? `${Number(event.expected_crowd).toLocaleString()} people`
                                        : "Not specified"}
                                </span>
                            </div>

                            <div className="event-hero-detail">
                                <strong>Schedule</strong>
                                <span>
                                    {event.start_date || "Ongoing"}
                                    {event.start_time ? ` at ${event.start_time}` : ""}
                                </span>
                            </div>

                            {event.end_date && (
                                <div className="event-hero-detail">
                                    <strong>Concludes</strong>
                                    <span>
                                        {event.end_date}
                                        {event.end_time ? ` at ${event.end_time}` : ""}
                                    </span>
                                </div>
                            )}
                        </div>

                        {event.description && (
                            <p className="event-hero-desc">{event.description}</p>
                        )}
                    </div>
                </section>

                {/* Live Situation Metrics */}
                <section className="section">
                    <div className="section-heading">
                        <p className="eyebrow">LIVE EVENT INTELLIGENCE</p>
                        <h2>Current Crowd Situation</h2>
                        <p>Real-time analytics streamed from the AI crowd monitoring engine.</p>
                    </div>

                    <div className="stats-grid">
                        <div className="stat-card">
                            <span>👥</span>
                            <h3>{crowd?.total_people ?? 0}</h3>
                            <p>People Detected</p>
                        </div>

                        <div className="stat-card">
                            <span>📐</span>
                            <h3>{crowd?.spatial?.usable_area_m2 ?? crowd?.usable_area_m2 ?? 0} m²</h3>
                            <p>Usable Area ({crowd?.crowd?.density_pm2 ?? crowd?.people_per_m2 ?? 0} p/m²)</p>
                        </div>

                        <div className="stat-card">
                            <span>📈</span>
                            <h3>{crowd?.temporal?.trend || crowd?.crowd?.trend || "STABLE"}</h3>
                            <p>
                                Growth: {crowd?.temporal?.growth_rate ? (crowd.temporal.growth_rate > 0 ? `+${crowd.temporal.growth_rate}/min` : `${crowd.temporal.growth_rate}/min`) : "0.0/min"}
                            </p>
                        </div>

                        <div className="stat-card">
                            <span>🔮</span>
                            <h3>~{crowd?.forecast?.projected_people_5min ?? crowd?.total_people ?? 0}</h3>
                            <p>5-Min Forecast (Proto)</p>
                        </div>

                        <div className="stat-card">
                            <span>⚡</span>
                            <h3>{crowd?.forecast?.rush_forecast || "LOW"}</h3>
                            <p>Rush Likelihood</p>
                        </div>

                        <div className="stat-card">
                            <span>⚠</span>
                            <h3>{crowd?.overall_risk ?? 0}/100</h3>
                            <p>
                                Risk <RiskBadge level={crowd?.overall_risk_level || "SAFE"} />
                            </p>
                        </div>
                    </div>

                    {crowd?.timestamp && (
                        <p className="live-timestamp">
                            Last synchronized: {crowd.timestamp}
                        </p>
                    )}
                </section>

                {/* 2x2 Zone Grid */}
                <section className="section">
                    <div className="section-heading">
                        <p className="eyebrow">ZONE ANALYSIS</p>
                        <h2>2×2 Crowd Intelligence Map</h2>
                        <p>
                            Event area segmented into 4 independent monitoring zones for density,
                            flow and early risk estimation.
                        </p>
                    </div>

                    <div className="heatmap-grid">
                        {[0, 1, 2, 3].map((index) => {
                            const zone = zones[index] || {
                                zone: index,
                                people: 0,
                                density: "LOW",
                                dominant_direction: "STATIONARY",
                                trend: "STABLE",
                                congestion: "LOW",
                                usable_area_m2: 0,
                                net_flow: 0,
                                risk: 0,
                                risk_level: "SAFE",
                            };

                            const zUsable = zone.usable_area_m2;
                            const zNet = zone.net_flow ?? 0;

                            return (
                                <div
                                    className={`heatmap-zone risk-${(
                                        zone.risk_level || "SAFE"
                                    ).toLowerCase()}`}
                                    key={index}
                                >
                                    <div className="zone-header">
                                        <h3>Zone {index}</h3>
                                        <RiskBadge level={zone.risk_level} />
                                    </div>

                                    <div className="zone-main-number">{zone.people ?? 0}</div>
                                    <p>People</p>

                                    <div className="zone-details">
                                        <div>
                                            <strong>Usable Space</strong>
                                            <span>{zUsable > 0 ? `${zUsable.toFixed(1)} m²` : (zone.floor_area_m2 > 0 ? `${zone.floor_area_m2.toFixed(1)} m²` : "Outside floor")}</span>
                                        </div>

                                        <div>
                                            <strong>Flow</strong>
                                            <span>{zone.dominant_direction || zone.flow || "STATIONARY"} {zNet !== 0 ? `(${zNet > 0 ? `+${zNet}` : zNet})` : ""}</span>
                                        </div>

                                        <div>
                                            <strong>Density</strong>
                                            <span>{zone.density || "LOW"}</span>
                                        </div>

                                        <div>
                                            <strong>Trend</strong>
                                            <span>{zone.concentration_trend || zone.trend || "STABLE"}</span>
                                        </div>
                                    </div>

                                    <div className="zone-risk-score">
                                        Risk Score: <strong>{zone.risk ?? 0}/100</strong>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </section>

                {/* Safety Intelligence */}
                <section className="section">
                    <div className="section-heading">
                        <p className="eyebrow">SAFETY INTELLIGENCE</p>
                        <h2>Operational Safety Assessment</h2>
                    </div>

                    <div className="safety-card">
                        <div className="safety-score">
                            <strong>{crowd?.overall_risk ?? 0}</strong>
                            <span>/100</span>
                        </div>

                        <div>
                            <RiskBadge level={crowd?.overall_risk_level || "SAFE"} />
                            <p>
                                {crowd?.overall_risk_level === "CRITICAL"
                                    ? "Critical crowd density detected. Immediate crowd redirection may be required."
                                    : crowd?.overall_risk_level === "HIGH"
                                    ? "High crowd activity detected. Monitoring team advised to stay alert."
                                    : crowd?.overall_risk_level === "MODERATE"
                                    ? "Moderate crowd flow. Conditions are steady and monitored."
                                    : "Current event crowd conditions are well within monitored safety limits."}
                            </p>
                        </div>
                    </div>
                </section>
            </main>

            <footer className="footer">
                <div>
                    <strong>AI Crowd Intelligence</strong>
                    <p>AI-powered crowd monitoring and early-warning system.</p>
                </div>

                <div>
                    <p>© 2026 AI Crowd Intelligence</p>
                </div>
            </footer>
        </>
    );
}

export default EventPage;
