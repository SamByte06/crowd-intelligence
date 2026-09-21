import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

const places = {
    mahakaleshwar: {
        name: "Mahakaleshwar Temple",
        location: "Ujjain, Madhya Pradesh",
        description:
            "AI-powered crowd intelligence for monitoring crowd density, movement and changing risk conditions.",
        image: "/images/mahakaleshwar.jpg",
    },

    stadium: {
        name: "City Stadium",
        location: "Bhopal, Madhya Pradesh",
        description:
            "Real-time crowd monitoring and movement intelligence for large public gatherings.",
        image: "/images/stadium.jpg",
    },

    festival: {
        name: "Festival Ground",
        location: "Bhopal, Madhya Pradesh",
        description:
            "Crowd monitoring and early-warning intelligence for festivals and public events.",
        image: "/images/festival.jpg",
    },
};

function useLiveCrowd() {
    const [crowd, setCrowd] = useState(null);

    useEffect(() => {
        let active = true;

        const fetchCrowd = async () => {
            try {
                const response = await fetch(
                    "https://crowd-intelligence-back.vercel.app"
                );

                if (!response.ok) {
                    throw new Error("Backend unavailable");
                }

                const data = await response.json();

                if (active) {
                    setCrowd(data);
                }
            } catch (error) {
                console.log("Crowd data unavailable");
            }
        };

        fetchCrowd();

        const interval = setInterval(fetchCrowd, 1000);

        return () => {
            active = false;
            clearInterval(interval);
        };
    }, []);

    return crowd;
}

function RiskBadge({ level }) {
    const riskLevel = level || "WAITING";

    return (
        <span className={`risk-badge risk-${riskLevel.toLowerCase()}`}>
            {riskLevel}
        </span>
    );
}

function LiveStatus({ crowd }) {
    if (!crowd) {
        return (
            <section className="section">
                <div className="section-heading">
                    <p className="eyebrow">LIVE STATUS</p>
                    <h2>Connecting to AI Engine...</h2>
                    <p>
                        Waiting for the latest crowd intelligence from the
                        monitoring system.
                    </p>
                </div>
            </section>
        );
    }

    return (
        <section className="section">
            <div className="section-heading">
                <p className="eyebrow">LIVE STATUS</p>
                <h2>Current Crowd Situation</h2>
                <p>
                    Latest information received from the AI crowd intelligence
                    engine.
                </p>
            </div>

            <div className="stats-grid">
                <div className="stat-card">
                    <span>👥</span>
                    <h3>{crowd.total_people ?? 0}</h3>
                    <p>People Detected</p>
                </div>

                <div className="stat-card">
                    <span>⚠</span>
                    <h3>{crowd.overall_risk ?? 0}/100</h3>
                    <p>
                        Risk{" "}
                        <RiskBadge
                            level={crowd.overall_risk_level}
                        />
                    </p>
                </div>

                <div className="stat-card">
                    <span>↗</span>
                    <h3>{crowd.highest_risk_zone ?? 0}</h3>
                    <p>Highest Risk Zone</p>
                </div>

                <div className="stat-card">
                    <span>●</span>
                    <h3>{crowd.alert || "NO ALERT"}</h3>
                    <p>Alert Status</p>
                </div>
            </div>

            {crowd.timestamp && (
                <p className="live-timestamp">
                    Last updated: {crowd.timestamp}
                </p>
            )}
        </section>
    );
}

function ZoneAnalysis({ crowd }) {
    const zones = crowd?.zones || [];

    return (
        <section className="section">
            <div className="section-heading">
                <p className="eyebrow">ZONE ANALYSIS</p>
                <h2>2×2 Crowd Intelligence Map</h2>
                <p>
                    Each monitoring zone is analyzed independently for
                    density, movement, congestion and risk.
                </p>
            </div>

            <div className="heatmap-grid">
                {[0, 1, 2, 3].map((index) => {
                    const zone = zones[index];

                    if (!zone) {
                        return (
                            <div className="heatmap-zone" key={index}>
                                <h3>Zone {index}</h3>
                                <p>Waiting for data...</p>
                            </div>
                        );
                    }

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

                            <div className="zone-main-number">
                                {zone.people ?? 0}
                            </div>

                            <p>People</p>

                            <div className="zone-details">
                                <div>
                                    <strong>Density</strong>
                                    <span>{zone.density || "LOW"}</span>
                                </div>

                                <div>
                                    <strong>Trend</strong>
                                    <span>{zone.trend || "STABLE"}</span>
                                </div>

                                <div>
                                    <strong>Flow</strong>
                                    <span>
                                        {zone.dominant_direction ||
                                            "STATIONARY"}
                                    </span>
                                </div>

                                <div>
                                    <strong>Congestion</strong>
                                    <span>
                                        {zone.congestion || "LOW"}
                                    </span>
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
    );
}

function HistoricalSection() {
    return (
        <section className="section">
            <div className="section-heading">
                <p className="eyebrow">HISTORICAL INTELLIGENCE</p>
                <h2>Historical Crowd Patterns</h2>
                <p>
                    Previous crowd behavior can be used to understand expected
                    patterns for recurring events and locations.
                </p>
            </div>

            <div className="history-card">
                <div>
                    <span>📅</span>
                    <h3>Historical Analysis</h3>
                    <p>
                        Historical event data will be combined with current
                        crowd conditions as the intelligence system develops.
                    </p>
                </div>

                <div className="history-placeholder">
                    Historical pattern model
                    <strong>Preparing</strong>
                </div>
            </div>
        </section>
    );
}

function RushForecast() {
    return (
        <section className="section">
            <div className="section-heading">
                <p className="eyebrow">FORECAST</p>
                <h2>Rush Forecast</h2>
                <p>
                    Future versions of the intelligence engine will combine
                    current crowd trends with historical patterns to estimate
                    possible crowd growth.
                </p>
            </div>

            <div className="forecast-card">
                <div>
                    <span>📈</span>
                    <h3>Rush Forecast</h3>
                    <p>
                        Forecasting intelligence will be displayed here when
                        the temporal forecasting model is connected.
                    </p>
                </div>

                <strong>Preparing</strong>
            </div>
        </section>
    );
}

function SafetySection({ crowd }) {
    const risk = crowd?.overall_risk ?? 0;
    const level = crowd?.overall_risk_level || "SAFE";

    let message =
        "Current crowd conditions are within the monitored safe range.";

    if (level === "MODERATE") {
        message =
            "Crowd conditions require continued monitoring as conditions are changing.";
    }

    if (level === "HIGH") {
        message =
            "Crowd conditions require increased attention and monitoring.";
    }

    if (level === "CRITICAL") {
        message =
            "Critical crowd conditions detected. Immediate operational attention may be required.";
    }

    return (
        <section className="section">
            <div className="section-heading">
                <p className="eyebrow">SAFETY INTELLIGENCE</p>
                <h2>Safety Status</h2>
            </div>

            <div className="safety-card">
                <div className="safety-score">
                    <strong>{risk}</strong>
                    <span>/100</span>
                </div>

                <div>
                    <RiskBadge level={level} />
                    <p>{message}</p>
                </div>
            </div>
        </section>
    );
}

function Facilities() {
    return (
        <section className="section">
            <div className="section-heading">
                <p className="eyebrow">LOCATION INFORMATION</p>
                <h2>Facilities</h2>
            </div>

            <div className="facilities-grid">
                <div className="facility-card">
                    <span>📹</span>
                    <h3>Camera Monitoring</h3>
                    <p>AI-based visual crowd monitoring.</p>
                </div>

                <div className="facility-card">
                    <span>📊</span>
                    <h3>Crowd Analytics</h3>
                    <p>Density, movement and congestion analysis.</p>
                </div>

                <div className="facility-card">
                    <span>⚠</span>
                    <h3>Early Warning</h3>
                    <p>Risk and alert intelligence for operators.</p>
                </div>
            </div>
        </section>
    );
}

function EventSection() {
    return (
        <section className="section">
            <div className="event-card">
                <div>
                    <p className="eyebrow">EVENT INTELLIGENCE</p>
                    <h2>Monitoring Event Conditions</h2>
                    <p>
                        Event-specific crowd intelligence can be configured
                        through the administration system.
                    </p>
                </div>

                <span className="event-status">MONITORING</span>
            </div>
        </section>
    );
}

function Footer() {
    return (
        <footer className="footer">
            <div>
                <strong>AI Crowd Intelligence</strong>
                <p>
                    AI-powered crowd monitoring and early-warning intelligence.
                </p>
            </div>

            <div>
                <p>© 2026 AI Crowd Intelligence</p>
            </div>
        </footer>
    );
}

function PlacePage() {
    const { placeId } = useParams();
    const navigate = useNavigate();

    const crowd = useLiveCrowd();

    const place = places[placeId];

    if (!place) {
        return (
            <div className="section">
                <h2>Place not found</h2>

                <button
                    className="nav-link-button"
                    onClick={() => navigate("/")}
                >
                    Back to Home
                </button>
            </div>
        );
    }

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
                <section className="place-hero">
                    <img src={place.image} alt={place.name} />

                    <div className="place-hero-content">
                        <button
                            className="back-button"
                            onClick={() => navigate("/")}
                        >
                            ← Back
                        </button>

                        <p className="eyebrow">MONITORED LOCATION</p>

                        <h1>{place.name}</h1>

                        <p className="place-location">
                            📍 {place.location}
                        </p>

                        <p>{place.description}</p>
                    </div>
                </section>

                <LiveStatus crowd={crowd} />

                <ZoneAnalysis crowd={crowd} />

                <HistoricalSection />

                <RushForecast />

                <SafetySection crowd={crowd} />

                <Facilities />

                <EventSection />
            </main>

            <Footer />
        </>
    );
}

export default PlacePage;